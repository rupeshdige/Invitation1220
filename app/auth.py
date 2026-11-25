from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .extensions import db, login_manager
from .models import User

bp = Blueprint("auth", __name__, url_prefix="/admin")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def _safe_next(target: str):
    if not target:
        return None
    parsed = urlparse(target)
    return target if not parsed.netloc and not parsed.scheme and target.startswith("/") and not target.startswith("//") else None


def signup_allowed() -> bool:
    return User.query.count() == 0 or current_app.config["ALLOW_SIGNUP"]


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user, remember=bool(request.form.get("remember")))
            return redirect(_safe_next(request.args.get("next")) or url_for("admin.dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("auth/login.html", can_signup=signup_allowed())


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))
    if not signup_allowed():
        flash("Sign-ups are closed. Ask the site owner for an account.", "error")
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        if not name or "@" not in email:
            flash("Please enter your name and a valid email.", "error")
        elif len(pw) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif pw != request.form.get("confirm", ""):
            flash("Passwords do not match.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(name=name, email=email)
            user.set_password(pw)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Welcome! Your account is ready — create your first invitation.", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("auth/register.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
