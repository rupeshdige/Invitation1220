from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy.orm import deferred
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow() -> datetime:
    """Naive UTC timestamp (stored as-is; converted to local time only for display)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


DEFAULT_SHARE = (
    "Dear {name},\n\n{hosts} warmly invite you. "
    "Please open your personal invitation and kindly confirm your presence:\n{link}"
)
DEFAULT_REMINDER = (
    "Dear {name}, a gentle reminder to kindly confirm your presence for {title}. "
    "Your personal invitation: {link}"
)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    events = db.relationship("Event", backref="owner", cascade="all, delete-orphan", lazy="select")

    def set_password(self, pw: str) -> None:
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw: str) -> bool:
        return check_password_hash(self.password_hash, pw)


class Event(db.Model):
    """One invitation design + its guest list."""
    __tablename__ = "events"
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # content
    title = db.Column(db.String(160), nullable=False)
    name_one = db.Column(db.String(80), default="")
    name_two = db.Column(db.String(80), default="")
    subtitle = db.Column(db.String(240), default="")
    header_text = db.Column(db.String(240), default="")
    seal_text = db.Column(db.String(8), default="")
    hosts = db.Column(db.String(200), default="")
    intro_line = db.Column(db.String(160), default="With love, we invite")
    message = db.Column(db.Text, default="")
    rsvp_note = db.Column(db.Text, default="")
    closing_line = db.Column(db.String(160), default="With love & duas")
    thanks_text = db.Column(db.String(240), default="Your reply has reached the family.")
    date_text = db.Column(db.String(120), default="")
    venue = db.Column(db.String(200), default="")
    venue_address = db.Column(db.String(300), default="")
    venue_map_url = db.Column(db.String(500), default="")
    rsvp_deadline = db.Column(db.Date, nullable=True)
    rsvp_open = db.Column(db.Boolean, default=True, nullable=False)

    # theme
    bg_color = db.Column(db.String(9), default="#f6f4e2")
    paper_color = db.Column(db.String(9), default="#fffdf4")
    text_color = db.Column(db.String(9), default="#3b3a30")
    accent_color = db.Column(db.String(9), default="#a8863c")
    envelope_color = db.Column(db.String(9), default="#d9cfa6")
    font_heading = db.Column(db.String(60), default="Cormorant Garamond")
    font_script = db.Column(db.String(60), default="Great Vibes")
    font_body = db.Column(db.String(60), default="Jost")

    # image slots (ids in `media`)
    header_media_id = db.Column(db.Integer, nullable=True)
    hero_media_id = db.Column(db.Integer, nullable=True)
    bg_media_id = db.Column(db.Integer, nullable=True)

    # sharing
    country_code = db.Column(db.String(5), default="91")
    share_message = db.Column(db.Text, default=DEFAULT_SHARE)
    reminder_message = db.Column(db.Text, default=DEFAULT_REMINDER)

    created_at = db.Column(db.DateTime, default=utcnow)

    functions = db.relationship(
        "Function", backref="event", cascade="all, delete-orphan",
        order_by="(Function.sort_order, Function.starts_at, Function.id)",
    )
    guests = db.relationship("Guest", backref="event", cascade="all, delete-orphan", order_by="Guest.id")
    media = db.relationship("Media", backref="event", cascade="all, delete-orphan")
    activity = db.relationship("Activity", backref="event", cascade="all, delete-orphan")

    @property
    def display_names(self) -> str:
        names = [n for n in (self.name_one, self.name_two) if n]
        return " & ".join(names) if names else self.title

    @property
    def monogram(self) -> str:
        if self.seal_text:
            return self.seal_text
        return "".join(n.strip()[0].upper() for n in (self.name_one, self.name_two) if n and n.strip())[:3] or "✦"


class Function(db.Model):
    """A single occasion inside an event (nikah, reception, mehndi, ...)."""
    __tablename__ = "functions"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    venue = db.Column(db.String(200), default="")
    address = db.Column(db.String(300), default="")
    map_url = db.Column(db.String(500), default="")
    dress_code = db.Column(db.String(160), default="")
    notes = db.Column(db.String(400), default="")
    sort_order = db.Column(db.Integer, default=0)
    rsvps = db.relationship("GuestFunction", backref="function", cascade="all, delete-orphan")


class Guest(db.Model):
    __tablename__ = "guests"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    slug = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(40), default="")
    email = db.Column(db.String(190), default="")
    group_name = db.Column(db.String(80), default="")
    max_guests = db.Column(db.Integer, default=1, nullable=False)

    sent_at = db.Column(db.DateTime, nullable=True)
    first_opened_at = db.Column(db.DateTime, nullable=True)
    last_opened_at = db.Column(db.DateTime, nullable=True)
    open_count = db.Column(db.Integer, default=0, nullable=False)

    response = db.Column(db.String(12), default="pending", nullable=False)  # pending|attending|declined
    party_size = db.Column(db.Integer, default=0, nullable=False)
    responded_at = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.String(1000), default="")
    admin_note = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=utcnow)

    rsvps = db.relationship("GuestFunction", backref="guest", cascade="all, delete-orphan")

    @property
    def rsvp_map(self) -> dict:
        return {r.function_id: r.count for r in self.rsvps}


class GuestFunction(db.Model):
    __tablename__ = "guest_functions"
    __table_args__ = (db.UniqueConstraint("guest_id", "function_id", name="uq_guest_function"),)
    id = db.Column(db.Integer, primary_key=True)
    guest_id = db.Column(db.Integer, db.ForeignKey("guests.id"), nullable=False, index=True)
    function_id = db.Column(db.Integer, db.ForeignKey("functions.id"), nullable=False, index=True)
    count = db.Column(db.Integer, default=0, nullable=False)  # 0 = not attending


class Media(db.Model):
    """Uploaded images are stored in PostgreSQL so they survive serverless deploys."""
    __tablename__ = "media"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)  # header|hero|bg|gallery
    mime = db.Column(db.String(60), default="image/webp")
    data = deferred(db.Column(db.LargeBinary, nullable=False))
    created_at = db.Column(db.DateTime, default=utcnow)


class Activity(db.Model):
    __tablename__ = "activity"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    guest_id = db.Column(db.Integer, nullable=True)
    guest_name = db.Column(db.String(160), default="")
    kind = db.Column(db.String(20), nullable=False)  # opened|replied|changed
    detail = db.Column(db.String(300), default="")
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
