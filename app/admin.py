import csv
import io

from flask import (Blueprint, Response, abort, flash, redirect, render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy.orm import defer

from .extensions import db
from .models import Activity, Event, Function, Guest, GuestFunction, Media, User, utcnow
from .services import event_stats, load_guests, recent_activity
from .utils import (BODY_FONTS, HEADING_FONTS, SCRIPT_FONTS, THEMES, ImageError, guest_link, new_guest_slug,
                    normalize_phone, parse_dt, parse_guest_lines, safe_url, save_media, to_int, valid_color,
                    whatsapp_link)

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
@login_required
def _guard():
    pass


def own_event(event_id: int) -> Event:
    ev = db.session.get(Event, event_id)
    if not ev or ev.owner_id != current_user.id:
        abort(404)
    return ev


def own_guest(ev: Event, guest_id: int) -> Guest:
    g = db.session.get(Guest, guest_id)
    if not g or g.event_id != ev.id:
        abort(404)
    return g


# ------------------------------------------------------------------ dashboard
@bp.route("/")
def dashboard():
    events = Event.query.filter_by(owner_id=current_user.id).order_by(Event.created_at.desc()).all()
    cards = [(ev, event_stats(ev)) for ev in events]
    return render_template("admin/dashboard.html", cards=cards)


# ------------------------------------------------------------------ event create / edit
TEXT_FIELDS = {
    "title": 160, "name_one": 80, "name_two": 80, "subtitle": 240, "header_text": 240, "seal_text": 8,
    "hosts": 200, "venue": 200, "venue_address": 300, "intro_line": 160, "closing_line": 160, "thanks_text": 240, "date_text": 120, "country_code": 5,
    "font_heading": 60, "font_script": 60, "font_body": 60,
}
LONG_FIELDS = {"message": 4000, "rsvp_note": 1500, "share_message": 1500, "reminder_message": 1500}
COLOR_FIELDS = ["bg_color", "paper_color", "text_color", "accent_color", "envelope_color"]
IMAGE_SLOTS = [("header", "header_media_id", 1400), ("hero", "hero_media_id", 1600), ("bg", "bg_media_id", 2000)]


def apply_event_form(ev: Event) -> bool:
    f = request.form
    for k, n in TEXT_FIELDS.items():
        if k in f:
            setattr(ev, k, f.get(k, "").strip()[:n])
    for k, n in LONG_FIELDS.items():
        if k in f:
            setattr(ev, k, f.get(k, "").strip()[:n])
    for k in COLOR_FIELDS:
        if k in f:
            setattr(ev, k, valid_color(f.get(k), getattr(ev, k)))
    if not ev.title:
        ev.title = (ev.display_names or "My invitation")[:160]
    if ev.font_heading not in HEADING_FONTS:
        ev.font_heading = HEADING_FONTS[0]
    if ev.font_script not in SCRIPT_FONTS:
        ev.font_script = SCRIPT_FONTS[0]
    if ev.font_body not in BODY_FONTS:
        ev.font_body = BODY_FONTS[0]
    ev.venue_map_url = safe_url(f.get("venue_map_url", ""))[:500] if "venue_map_url" in f else ev.venue_map_url
    dl = parse_dt(f.get("rsvp_deadline", ""))
    ev.rsvp_deadline = dl.date() if dl else None
    ev.rsvp_open = bool(f.get("rsvp_open"))
    ev.country_code = "".join(c for c in (ev.country_code or "") if c.isdigit())

    db.session.flush()
    ok = True
    for kind, attr, size in IMAGE_SLOTS:
        if f.get(f"remove_{kind}"):
            Media.query.filter_by(event_id=ev.id, kind=kind).delete()
            setattr(ev, attr, None)
        upload = request.files.get(kind)
        if upload and upload.filename:
            try:
                m = save_media(ev, kind, upload, single=True, max_side=size)
                setattr(ev, attr, m.id)
            except ImageError as e:
                flash(f"{kind.title()} image: {e}", "error")
                ok = False
    return ok


@bp.route("/events/new", methods=["GET", "POST"])
def event_new():
    ev = Event(owner_id=current_user.id, title="")
    if request.method == "POST":
        db.session.add(ev)
        apply_event_form(ev)
        db.session.commit()
        flash("Invitation created. Add your functions and guests next.", "success")
        return redirect(url_for("admin.event_functions", event_id=ev.id))
    return render_template("admin/event_form.html", ev=ev, is_new=True, themes=THEMES,
                           heading_fonts=HEADING_FONTS, script_fonts=SCRIPT_FONTS, body_fonts=BODY_FONTS)


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
def event_edit(event_id):
    ev = own_event(event_id)
    if request.method == "POST":
        apply_event_form(ev)
        db.session.commit()
        flash("Design & content saved.", "success")
        return redirect(url_for("admin.event_edit", event_id=ev.id))
    return render_template("admin/event_form.html", ev=ev, is_new=False, themes=THEMES,
                           heading_fonts=HEADING_FONTS, script_fonts=SCRIPT_FONTS, body_fonts=BODY_FONTS)


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
def event_delete(event_id):
    ev = own_event(event_id)
    if request.form.get("confirm", "").strip().lower() != "delete":
        flash("Type DELETE to confirm removing the invitation.", "error")
        return redirect(url_for("admin.event_edit", event_id=ev.id))
    db.session.delete(ev)
    db.session.commit()
    flash("Invitation deleted.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/events/<int:event_id>/duplicate", methods=["POST"])
def event_duplicate(event_id):
    src = own_event(event_id)
    cols = [c.name for c in Event.__table__.columns if c.name not in ("id", "created_at", "owner_id",
            "header_media_id", "hero_media_id", "bg_media_id", "title")]
    new = Event(owner_id=current_user.id, title=f"{src.title} (copy)", **{c: getattr(src, c) for c in cols})
    db.session.add(new)
    db.session.flush()
    for fn in src.functions:
        db.session.add(Function(event_id=new.id, name=fn.name, starts_at=fn.starts_at, ends_at=fn.ends_at, venue=fn.venue,
                                address=fn.address, map_url=fn.map_url, dress_code=fn.dress_code, notes=fn.notes,
                                sort_order=fn.sort_order))
    for kind, attr, _ in IMAGE_SLOTS:
        old_id = getattr(src, attr)
        old = db.session.get(Media, old_id) if old_id else None
        if old:
            m = Media(event_id=new.id, kind=kind, mime=old.mime, data=old.data)
            db.session.add(m)
            db.session.flush()
            setattr(new, attr, m.id)
    db.session.commit()
    flash("Invitation duplicated (guests are not copied).", "success")
    return redirect(url_for("admin.event_edit", event_id=new.id))


# ------------------------------------------------------------------ tracker overview
@bp.route("/events/<int:event_id>")
def event_overview(event_id):
    ev = own_event(event_id)
    guests = load_guests(ev.id)
    stats = event_stats(ev, guests)
    follow_up = [g for g in guests if g.response == "pending"]
    follow_up.sort(key=lambda g: (g.open_count == 0, g.sent_at is None))
    wishes = sorted([g for g in guests if g.note], key=lambda g: g.responded_at or g.created_at, reverse=True)
    return render_template("admin/event_overview.html", ev=ev, stats=stats, follow_up=follow_up[:12], wishes=wishes,
                           activity=recent_activity(ev.id), whatsapp_link=whatsapp_link, guest_link=guest_link)


# ------------------------------------------------------------------ functions
@bp.route("/events/<int:event_id>/functions", methods=["GET", "POST"])
def event_functions(event_id):
    ev = own_event(event_id)
    edit_id = to_int(request.args.get("edit"), 0)
    editing = next((fn for fn in ev.functions if fn.id == edit_id), None)
    if request.method == "POST":
        fid = to_int(request.form.get("function_id"), 0)
        fn = next((x for x in ev.functions if x.id == fid), None) or Function(event_id=ev.id)
        name = request.form.get("name", "").strip()
        if not name:
            flash("Give the function a name (e.g. Nikah, Reception).", "error")
            return redirect(url_for("admin.event_functions", event_id=ev.id, edit=fid or None))
        fn.name = name[:120]
        fn.starts_at = parse_dt(request.form.get("starts_at"))
        fn.ends_at = parse_dt(request.form.get("ends_at"))
        fn.venue = request.form.get("venue", "").strip()[:200]
        fn.address = request.form.get("address", "").strip()[:300]
        fn.map_url = safe_url(request.form.get("map_url"))[:500]
        fn.dress_code = request.form.get("dress_code", "").strip()[:160]
        fn.notes = request.form.get("notes", "").strip()[:400]
        fn.sort_order = to_int(request.form.get("sort_order"), 0)
        if not fn.id:
            db.session.add(fn)
        db.session.commit()
        flash("Function saved.", "success")
        return redirect(url_for("admin.event_functions", event_id=ev.id))
    return render_template("admin/functions.html", ev=ev, editing=editing)


@bp.route("/events/<int:event_id>/functions/<int:fid>/delete", methods=["POST"])
def function_delete(event_id, fid):
    ev = own_event(event_id)
    fn = db.session.get(Function, fid)
    if not fn or fn.event_id != ev.id:
        abort(404)
    db.session.delete(fn)
    db.session.commit()
    flash("Function removed (and its RSVPs).", "success")
    return redirect(url_for("admin.event_functions", event_id=ev.id))


# ------------------------------------------------------------------ gallery
@bp.route("/events/<int:event_id>/gallery", methods=["GET", "POST"])
def event_gallery(event_id):
    ev = own_event(event_id)
    if request.method == "POST":
        added = 0
        for up in request.files.getlist("photos"):
            if not up or not up.filename:
                continue
            try:
                save_media(ev, "gallery", up, single=False, max_side=1600)
                added += 1
            except ImageError as e:
                flash(f"{up.filename}: {e}", "error")
        db.session.commit()
        if added:
            flash(f"{added} photo(s) added.", "success")
        return redirect(url_for("admin.event_gallery", event_id=ev.id))
    photos = Media.query.options(defer(Media.data)).filter_by(event_id=ev.id, kind="gallery").order_by(Media.id).all()
    return render_template("admin/gallery.html", ev=ev, photos=photos)


@bp.route("/events/<int:event_id>/gallery/<int:media_id>/delete", methods=["POST"])
def gallery_delete(event_id, media_id):
    ev = own_event(event_id)
    m = db.session.get(Media, media_id)
    if not m or m.event_id != ev.id or m.kind != "gallery":
        abort(404)
    db.session.delete(m)
    db.session.commit()
    return redirect(url_for("admin.event_gallery", event_id=ev.id))


# ------------------------------------------------------------------ guests
STATUS_FILTERS = {
    "all": "All", "pending": "Awaiting reply", "attending": "Attending", "declined": "Declined",
    "not_sent": "Not sent yet", "no_open": "Sent, not opened", "opened_no_reply": "Opened, no reply",
}


def filter_guests(guests, status, q, group):
    out = []
    q = (q or "").lower().strip()
    for g in guests:
        if status == "pending" and g.response != "pending":
            continue
        if status in ("attending", "declined") and g.response != status:
            continue
        if status == "not_sent" and g.sent_at:
            continue
        if status == "no_open" and not (g.sent_at and g.open_count == 0 and g.response == "pending"):
            continue
        if status == "opened_no_reply" and not (g.open_count > 0 and g.response == "pending"):
            continue
        if group and g.group_name != group:
            continue
        if q and q not in g.name.lower() and q not in (g.phone or "") and q not in (g.group_name or "").lower():
            continue
        out.append(g)
    return out


@bp.route("/events/<int:event_id>/guests")
def event_guests(event_id):
    ev = own_event(event_id)
    all_guests = load_guests(ev.id)
    status = request.args.get("status", "all")
    q = request.args.get("q", "")
    group = request.args.get("group", "")
    guests = filter_guests(all_guests, status, q, group)
    groups = sorted({g.group_name for g in all_guests if g.group_name})
    return render_template("admin/guests.html", ev=ev, guests=guests, total=len(all_guests), groups=groups,
                           status=status, q=q, group=group, filters=STATUS_FILTERS,
                           guest_link=guest_link, whatsapp_link=whatsapp_link)


@bp.route("/events/<int:event_id>/guests/add", methods=["POST"])
def guest_add(event_id):
    ev = own_event(event_id)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Guest name is required.", "error")
        return redirect(url_for("admin.event_guests", event_id=ev.id))
    g = Guest(event_id=ev.id, name=name[:160], phone=request.form.get("phone", "").strip()[:40],
              email=request.form.get("email", "").strip()[:190], group_name=request.form.get("group_name", "").strip()[:80],
              max_guests=to_int(request.form.get("max_guests"), 1, 1, 20), slug=new_guest_slug(name))
    db.session.add(g)
    db.session.commit()
    flash(f"{g.name} added. Their personal link is ready.", "success")
    return redirect(url_for("admin.event_guests", event_id=ev.id))


@bp.route("/events/<int:event_id>/guests/import", methods=["POST"])
def guest_import(event_id):
    ev = own_event(event_id)
    blob = request.form.get("bulk", "")
    upload = request.files.get("csv_file")
    if upload and upload.filename:
        blob = upload.read().decode("utf-8-sig", errors="ignore")
    rows = parse_guest_lines(blob)
    if not rows:
        flash("Nothing to import. Use one guest per line: Name, Phone, Group, Seats.", "error")
        return redirect(url_for("admin.event_guests", event_id=ev.id))
    for r in rows[:1000]:
        db.session.add(Guest(event_id=ev.id, slug=new_guest_slug(r["name"]), **r))
        db.session.flush()
    db.session.commit()
    flash(f"{min(len(rows), 1000)} guests imported.", "success")
    return redirect(url_for("admin.event_guests", event_id=ev.id))


@bp.route("/events/<int:event_id>/guests/<int:gid>", methods=["GET", "POST"])
def guest_edit(event_id, gid):
    ev = own_event(event_id)
    g = own_guest(ev, gid)
    if request.method == "POST":
        g.name = request.form.get("name", "").strip()[:160] or g.name
        g.phone = request.form.get("phone", "").strip()[:40]
        g.email = request.form.get("email", "").strip()[:190]
        g.group_name = request.form.get("group_name", "").strip()[:80]
        g.max_guests = to_int(request.form.get("max_guests"), 1, 1, 20)
        g.admin_note = request.form.get("admin_note", "").strip()[:500]
        db.session.commit()
        flash("Guest updated.", "success")
        return redirect(url_for("admin.event_guests", event_id=ev.id))
    return render_template("admin/guest_edit.html", ev=ev, g=g, link=guest_link(g))


@bp.route("/events/<int:event_id>/guests/<int:gid>/action", methods=["POST"])
def guest_action(event_id, gid):
    ev = own_event(event_id)
    g = own_guest(ev, gid)
    action = request.form.get("action")
    if action == "sent":
        g.sent_at = utcnow()
    elif action == "unsent":
        g.sent_at = None
    elif action == "reset":
        for r in list(g.rsvps):
            db.session.delete(r)
        g.response, g.party_size, g.responded_at, g.note = "pending", 0, None, ""
    elif action == "delete":
        db.session.delete(g)
    db.session.commit()
    return redirect(request.form.get("back") or url_for("admin.event_guests", event_id=ev.id))


@bp.route("/events/<int:event_id>/guests/<int:gid>/mark-sent", methods=["POST"])
def guest_mark_sent(event_id, gid):
    """Called via fetch when the WhatsApp button is tapped."""
    ev = own_event(event_id)
    g = own_guest(ev, gid)
    if not g.sent_at:
        g.sent_at = utcnow()
        db.session.commit()
    return {"ok": True}


@bp.route("/events/<int:event_id>/guests/export.csv")
def guests_export(event_id):
    ev = own_event(event_id)
    guests = filter_guests(load_guests(ev.id), request.args.get("status", "all"), request.args.get("q"), request.args.get("group"))
    buf = io.StringIO()
    w = csv.writer(buf)
    fn_cols = [f.name for f in ev.functions]
    w.writerow(["Name", "Phone", "Email", "Group", "Seats allowed", "Status", "Attending (people)"] + fn_cols +
               ["Note from guest", "Sent", "First opened", "Times opened", "Replied at", "Invitation link"])
    for g in guests:
        m = g.rsvp_map
        w.writerow([g.name, normalize_phone(g.phone, ev.country_code) or g.phone, g.email, g.group_name, g.max_guests,
                    g.response, g.party_size] + [m.get(f.id, 0) if g.responded_at else "" for f in ev.functions] +
                   [g.note, g.sent_at.strftime("%Y-%m-%d %H:%M") if g.sent_at else "",
                    g.first_opened_at.strftime("%Y-%m-%d %H:%M") if g.first_opened_at else "", g.open_count,
                    g.responded_at.strftime("%Y-%m-%d %H:%M") if g.responded_at else "", guest_link(g)])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=guests-{ev.id}.csv"})


# ------------------------------------------------------------------ preview
@bp.route("/events/<int:event_id>/preview")
def event_preview(event_id):
    ev = own_event(event_id)
    sample = Guest(name="Guest Name", max_guests=4, slug="preview", response="pending")
    gallery = Media.query.options(defer(Media.data)).filter_by(event_id=ev.id, kind="gallery").order_by(Media.id).all()
    return render_template("guest/invite.html", ev=ev, guest=sample, functions=ev.functions, rsvp_map={},
                           gallery=gallery, preview=True)


# ------------------------------------------------------------------ system check
@bp.route("/system")
def system():
    from flask import current_app
    from sqlalchemy import text
    eng = db.engine
    info = {"dialect": eng.dialect.name, "host": eng.url.host or "local file", "database": eng.url.database}
    try:
        info["server"] = db.session.execute(text("select version()")).scalar() if eng.dialect.name == "postgresql" else "SQLite"
        info["ok"] = True
    except Exception as e:  # show the reason instead of a blank 500
        info["ok"], info["server"] = False, str(e)[:300]
    counts = {}
    if info["ok"]:
        counts = {"Your invitations": Event.query.filter_by(owner_id=current_user.id).count(), "All users": db.session.query(db.func.count(User.id)).scalar(),
                  "Guests (yours)": Guest.query.join(Event).filter(Event.owner_id == current_user.id).count(),
                  "Images stored": Media.query.join(Event).filter(Event.owner_id == current_user.id).count()}
    return render_template("admin/system.html", info=info, counts=counts, base_url=current_app.config["BASE_URL"] or "(not set - using the browser address)")


# ------------------------------------------------------------------ account
@bp.route("/account", methods=["GET", "POST"])
def account():
    if request.method == "POST":
        current_user.name = request.form.get("name", "").strip()[:120] or current_user.name
        new_pw = request.form.get("new_password", "")
        if new_pw:
            if not current_user.check_password(request.form.get("current_password", "")):
                flash("Current password is incorrect.", "error")
                return redirect(url_for("admin.account"))
            if len(new_pw) < 8:
                flash("New password must be at least 8 characters.", "error")
                return redirect(url_for("admin.account"))
            current_user.set_password(new_pw)
        db.session.commit()
        flash("Account updated.", "success")
        return redirect(url_for("admin.account"))
    return render_template("admin/account.html")
