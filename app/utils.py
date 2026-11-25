import csv
import io
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote, urlencode

from flask import current_app, url_for
from PIL import Image, ImageOps, UnidentifiedImageError

from .extensions import db
from .models import Guest, Media

Image.MAX_IMAGE_PIXELS = 40_000_000

# ---------- themes / fonts ----------
THEMES = {
    "ivory": {"label": "Ivory & Gold", "bg_color": "#f6f4e2", "paper_color": "#fffdf4", "text_color": "#3b3a30", "accent_color": "#a8863c", "envelope_color": "#d9cfa6"},
    "emerald": {"label": "Emerald Night", "bg_color": "#0f2a24", "paper_color": "#143a31", "text_color": "#efe7cf", "accent_color": "#d4b15f", "envelope_color": "#1d4d41"},
    "rose": {"label": "Blush Rose", "bg_color": "#f8e9e7", "paper_color": "#fff8f6", "text_color": "#4a2f33", "accent_color": "#b5656f", "envelope_color": "#eac5c4"},
    "navy": {"label": "Royal Navy", "bg_color": "#14213d", "paper_color": "#1b2c50", "text_color": "#f3ecd8", "accent_color": "#e0b869", "envelope_color": "#253a68"},
    "sage": {"label": "Sage Garden", "bg_color": "#e8ede1", "paper_color": "#fbfcf7", "text_color": "#2f3a2c", "accent_color": "#6f8a5b", "envelope_color": "#c9d6bb"},
    "maroon": {"label": "Maroon & Champagne", "bg_color": "#f3e8dc", "paper_color": "#fff9f1", "text_color": "#4a1f27", "accent_color": "#8c2f3d", "envelope_color": "#d8b9a3"},
}
HEADING_FONTS = ["Cormorant Garamond", "Playfair Display", "Cinzel", "Marcellus", "EB Garamond", "Lora"]
SCRIPT_FONTS = ["Great Vibes", "Allura", "Parisienne", "Pinyon Script", "Tangerine", "Alex Brush"]
BODY_FONTS = ["Jost", "Lato", "Raleway", "Montserrat", "Cormorant Garamond", "Nunito Sans"]


def google_fonts_url(ev) -> str:
    fams = []
    for name, weights in ((ev.font_heading, "400;500;600;700"), (ev.font_script, "400"), (ev.font_body, "300;400;500;600")):
        if name and name not in [f.split(":")[0].replace("+", " ") for f in fams]:
            fams.append(f"{name.replace(' ', '+')}:wght@{weights}" if weights != "400" else name.replace(" ", "+"))
    fams.append("Amiri:wght@400")
    return "https://fonts.googleapis.com/css2?" + "&".join(f"family={f}" for f in fams) + "&display=swap"


# ---------- text helpers ----------
def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:50] or "guest"


def new_guest_slug(name: str) -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    while True:
        slug = f"{slugify(name)}-" + "".join(secrets.choice(alphabet) for _ in range(5))
        if not Guest.query.filter_by(slug=slug).first():
            return slug


def normalize_phone(phone: str, country_code: str = "91") -> str:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if len(digits) == 10 and country_code:
        digits = country_code + digits
    return digits


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


def to_int(value, default=0, lo=None, hi=None) -> int:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def parse_dt(value: str):
    value = (value or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def valid_color(value: str, fallback: str) -> str:
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value or "") else fallback


def safe_url(value: str) -> str:
    value = (value or "").strip()
    return value if value.lower().startswith(("http://", "https://")) else ""


# ---------- images ----------
class ImageError(ValueError):
    pass


def process_image(file_storage, max_side: int = 1800) -> tuple[bytes, str]:
    """Validate, auto-rotate, downscale and re-encode an upload as WebP."""
    raw = file_storage.read()
    if not raw:
        raise ImageError("The file is empty.")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageError("That file is not a valid image (use JPG, PNG or WebP).")
    img = ImageOps.exif_transpose(img)
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA" if has_alpha else "RGB")
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=86, method=4)
    return out.getvalue(), "image/webp"


def save_media(event, kind: str, file_storage, single: bool = True, max_side: int = 1800) -> Media:
    data, mime = process_image(file_storage, max_side=max_side)
    if single:
        for old in Media.query.filter_by(event_id=event.id, kind=kind).all():
            db.session.delete(old)
    m = Media(event_id=event.id, kind=kind, mime=mime, data=data)
    db.session.add(m)
    db.session.flush()
    return m


# ---------- links / sharing ----------
def guest_link(guest) -> str:
    base = current_app.config.get("BASE_URL")
    path = url_for("public.invite", slug=guest.slug)
    if base:
        return base + path
    return url_for("public.invite", slug=guest.slug, _external=True)


def render_template_text(template: str, guest, event, link: str) -> str:
    values = {"name": guest.name, "link": link, "hosts": event.hosts or event.display_names, "title": event.title}
    out = template or ""
    for k, v in values.items():
        out = out.replace("{" + k + "}", v)
    return out


def whatsapp_link(guest, event, reminder: bool = False) -> str:
    link = guest_link(guest)
    tpl = event.reminder_message if reminder else event.share_message
    text = render_template_text(tpl, guest, event, link)
    phone = normalize_phone(guest.phone, event.country_code or "")
    return f"https://wa.me/{phone}?text={quote(text)}" if phone else f"https://wa.me/?text={quote(text)}"


def parse_guest_lines(blob: str):
    """Lines of: Name, Phone, Group, Seats  (comma or tab separated). Yields dicts."""
    rows = []
    for line in (blob or "").splitlines():
        line = line.strip()
        if not line:
            continue
        delim = "\t" if "\t" in line else ","
        parts = [p.strip() for p in next(csv.reader([line], delimiter=delim))]
        if not parts[0] or parts[0].lower() in ("name", "guest", "guest name"):
            continue
        rows.append({
            "name": parts[0][:160],
            "phone": parts[1][:40] if len(parts) > 1 else "",
            "group_name": parts[2][:80] if len(parts) > 2 else "",
            "max_guests": to_int(parts[3], 1, 1, 20) if len(parts) > 3 else 1,
        })
    return rows


# ---------- calendar + directions ----------
def _tz():
    return ZoneInfo(current_app.config["TIMEZONE"])


def _utc(dt) -> str:
    return dt.replace(tzinfo=_tz()).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_local(dt) -> str:
    return dt.replace(tzinfo=_tz()).isoformat() if dt else ""


def fn_location(fn) -> str:
    return ", ".join(x for x in (fn.venue, fn.address) if x)


def _fn_end(fn):
    return fn.ends_at or (fn.starts_at + timedelta(hours=3))


def gcal_url(fn, event) -> str:
    """Google Calendar 'add event' link (opens the Google Calendar app on Android)."""
    if not fn.starts_at:
        return ""
    params = {
        "action": "TEMPLATE",
        "text": f"{fn.name} · {event.display_names}",
        "dates": f"{_utc(fn.starts_at)}/{_utc(_fn_end(fn))}",
        "details": f"{event.title}. {fn.notes or ''}".strip() + (f"\nDirections: {fn.map_url}" if fn.map_url else ""),
        "location": fn_location(fn),
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params, quote_via=quote)


def google_directions_url(fn) -> str:
    loc = fn_location(fn)
    if not loc:
        return fn.map_url or ""
    return "https://www.google.com/maps/dir/?api=1&destination=" + quote(loc)


def apple_maps_url(fn) -> str:
    loc = fn_location(fn)
    return ("https://maps.apple.com/?daddr=" + quote(loc)) if loc else ""


def _ics_esc(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def build_ics(functions, event) -> str:
    """iCalendar file (Apple Calendar / iPhone, Outlook, Android) with reminders."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Invitation Studio//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for fn in functions:
        if not fn.starts_at:
            continue
        desc = f"{event.title}" + (f"\n{fn.notes}" if fn.notes else "") + (f"\nDirections: {fn.map_url}" if fn.map_url else "")
        lines += [
            "BEGIN:VEVENT", f"UID:fn{fn.id}-ev{event.id}@invitation-studio", f"DTSTAMP:{stamp}",
            f"DTSTART:{_utc(fn.starts_at)}", f"DTEND:{_utc(_fn_end(fn))}",
            f"SUMMARY:{_ics_esc(fn.name + ' · ' + event.display_names)}",
            f"LOCATION:{_ics_esc(fn_location(fn))}", f"DESCRIPTION:{_ics_esc(desc)}",
        ]
        if fn.map_url:
            lines.append(f"URL:{fn.map_url}")
        lines += ["BEGIN:VALARM", "TRIGGER:-P1D", "ACTION:DISPLAY", "DESCRIPTION:Tomorrow", "END:VALARM",
                  "BEGIN:VALARM", "TRIGGER:-PT3H", "ACTION:DISPLAY", "DESCRIPTION:Starting soon", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
