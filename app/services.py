"""Tracker maths used by the dashboard, event overview and CSV export."""
from sqlalchemy.orm import selectinload

from .models import Activity, Guest


def load_guests(event_id: int):
    return Guest.query.options(selectinload(Guest.rsvps)).filter_by(event_id=event_id).order_by(Guest.id).all()


def event_stats(event, guests=None) -> dict:
    guests = guests if guests is not None else load_guests(event.id)
    total = len(guests)
    attending = [g for g in guests if g.response == "attending"]
    declined = [g for g in guests if g.response == "declined"]
    responded = len(attending) + len(declined)
    stats = {
        "total": total,
        "seats": sum(g.max_guests for g in guests),
        "sent": sum(1 for g in guests if g.sent_at),
        "opened": sum(1 for g in guests if g.open_count > 0),
        "responded": responded,
        "pending": total - responded,
        "attending": len(attending),
        "declined": len(declined),
        "expected": sum(g.party_size for g in attending),
        "not_sent": sum(1 for g in guests if not g.sent_at),
        "opened_no_reply": sum(1 for g in guests if g.open_count > 0 and g.response == "pending"),
        "sent_not_opened": sum(1 for g in guests if g.sent_at and g.open_count == 0 and g.response == "pending"),
    }
    stats["response_pct"] = round(100 * responded / total) if total else 0
    stats["open_pct"] = round(100 * stats["opened"] / total) if total else 0

    per_fn = []
    for fn in event.functions:
        yes = headcount = 0
        for g in guests:
            for r in g.rsvps:
                if r.function_id == fn.id and r.count > 0:
                    yes += 1
                    headcount += r.count
        per_fn.append({"fn": fn, "parties": yes, "headcount": headcount})
    stats["per_function"] = per_fn
    return stats


def recent_activity(event_id: int, limit: int = 12):
    return Activity.query.filter_by(event_id=event_id).order_by(Activity.created_at.desc()).limit(limit).all()
