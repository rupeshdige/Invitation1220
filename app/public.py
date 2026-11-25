from datetime import timedelta

from flask import Blueprint, Response, abort, jsonify, render_template, request
from sqlalchemy.orm import defer

from .extensions import csrf, db
from .models import Activity, Guest, GuestFunction, Media, utcnow
from .utils import build_ics, slugify, to_int

bp = Blueprint("public", __name__)


def _guest_or_404(slug: str) -> Guest:
    g = Guest.query.filter_by(slug=slug).first()
    if not g:
        abort(404)
    return g


@bp.route("/i/<slug>")
def invite(slug):
    guest = _guest_or_404(slug)
    ev = guest.event
    gallery = Media.query.options(defer(Media.data)).filter_by(event_id=ev.id, kind="gallery").order_by(Media.id).all()
    resp = Response(render_template("guest/invite.html", ev=ev, guest=guest, functions=ev.functions,
                                    rsvp_map=guest.rsvp_map, gallery=gallery, preview=False))
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/i/<slug>/opened", methods=["POST"])
@csrf.exempt
def opened(slug):
    """Fired by JS when the guest taps the envelope (link-preview bots never run JS)."""
    g = _guest_or_404(slug)
    now = utcnow()
    first = g.first_opened_at is None
    # ignore rapid duplicates (double taps / reloads within 30 minutes)
    if first or (g.last_opened_at and now - g.last_opened_at > timedelta(minutes=30)):
        g.open_count += 1
        db.session.add(Activity(event_id=g.event_id, guest_id=g.id, guest_name=g.name, kind="opened",
                                detail="Opened the invitation" if first else "Opened again"))
    if first:
        g.first_opened_at = now
    g.last_opened_at = now
    if not g.sent_at:
        g.sent_at = now  # they clearly received it
    db.session.commit()
    return jsonify(ok=True)


@bp.route("/i/<slug>/rsvp", methods=["POST"])
@csrf.exempt
def rsvp(slug):
    g = _guest_or_404(slug)
    ev = g.event
    if not ev.rsvp_open:
        return jsonify(ok=False, error="Replies are closed for this invitation."), 403
    data = request.get_json(silent=True) or {}
    raw = data.get("functions") if isinstance(data.get("functions"), dict) else {}

    existing = {r.function_id: r for r in g.rsvps}
    counts = {}
    for fn in ev.functions:
        c = to_int(raw.get(str(fn.id)), 0, 0, g.max_guests)
        counts[fn.id] = c
        row = existing.get(fn.id)
        if row is None:
            row = GuestFunction(guest_id=g.id, function_id=fn.id)
            db.session.add(row)
        row.count = c

    if ev.functions:
        party = max(counts.values(), default=0)
    else:  # events without functions: single attendance question
        party = to_int(data.get("count"), 0, 0, g.max_guests)

    was_replied = g.responded_at is not None
    g.party_size = party
    g.response = "attending" if party > 0 else "declined"
    g.responded_at = utcnow()
    g.note = str(data.get("note", "")).strip()[:1000]
    if not g.sent_at:
        g.sent_at = g.responded_at
    detail = (f"Attending · {party} guest{'s' if party != 1 else ''}" if party else "Unable to attend")
    db.session.add(Activity(event_id=ev.id, guest_id=g.id, guest_name=g.name,
                            kind="changed" if was_replied else "replied", detail=detail))
    db.session.commit()
    return jsonify(ok=True, response=g.response, party=party)


def _ics_response(body: str, name: str) -> Response:
    return Response(body, mimetype="text/calendar",
                    headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "no-store"})


@bp.route("/i/<slug>/f/<int:fid>.ics")
def calendar_file(slug, fid):
    g = _guest_or_404(slug)
    fn = next((f for f in g.event.functions if f.id == fid), None)
    if not fn or not fn.starts_at:
        abort(404)
    return _ics_response(build_ics([fn], g.event), f"{slugify(fn.name)}.ics")


@bp.route("/i/<slug>/all.ics")
def calendar_all(slug):
    g = _guest_or_404(slug)
    return _ics_response(build_ics(g.event.functions, g.event), "invitation.ics")


@bp.route("/media/<int:media_id>")
def media(media_id):
    m = db.session.get(Media, media_id)
    if not m:
        abort(404)
    resp = Response(m.data, mimetype=m.mime)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp
