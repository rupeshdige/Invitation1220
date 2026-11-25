from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import click
from flask import Flask, redirect, render_template, url_for
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import IS_VERCEL, Config
from .extensions import csrf, db, login_manager
from .utils import (apple_maps_url, gcal_url, google_directions_url, google_fonts_url, iso_local, paragraphs)

_db_ready = False


def _add_missing_columns():
    """Tiny auto-migration: add new model columns to tables that already exist (SQLite & PostgreSQL)."""
    from sqlalchemy import inspect, text

    insp = inspect(db.engine)
    for table in db.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in have:
                ddl = col.type.compile(dialect=db.engine.dialect)
                with db.engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    if IS_VERCEL and app.config["SECRET_KEY"] == "dev-only-secret-change-me":
        raise RuntimeError("SECRET_KEY is not set. Add a long random value in Vercel environment variables.")

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."

    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    from .public import bp as public_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(public_bp)

    tz = ZoneInfo(app.config["TIMEZONE"])

    @app.template_filter("localtime")
    def localtime(dt, fmt="%d %b %Y, %I:%M %p"):
        if not dt:
            return "—"
        return dt.replace(tzinfo=timezone.utc).astimezone(tz).strftime(fmt)

    @app.template_filter("ago")
    def ago(dt):
        if not dt:
            return "—"
        secs = int((datetime.now(timezone.utc).replace(tzinfo=None) - dt).total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"

    @app.template_filter("dt")
    def fmt_dt(dt, fmt="%A, %d %B %Y"):
        return dt.strftime(fmt) if dt else ""

    @app.template_filter("tm")
    def fmt_tm(dt):
        return dt.strftime("%I:%M %p").lstrip("0") if dt else ""

    app.jinja_env.filters["paragraphs"] = paragraphs

    @app.context_processor
    def inject():
        return {"app_name": app.config["APP_NAME"], "gfonts": google_fonts_url, "gcal_url": gcal_url,
                "gmaps_dir": google_directions_url, "apple_maps": apple_maps_url, "iso_local": iso_local}

    @app.before_request
    def ensure_tables():
        global _db_ready
        if not _db_ready:
            try:
                db.create_all()
            except Exception:  # another cold-start instance may be creating the same tables
                db.session.rollback()
            try:
                _add_missing_columns()
            except Exception:
                db.session.rollback()
            _db_ready = True

    @app.route("/")
    def home():
        return redirect(url_for("admin.dashboard" if current_user.is_authenticated else "auth.login"))

    @app.route("/health")
    def health():
        return {"ok": True}

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("404.html", message="That upload is too large."), 413

    @app.cli.command("init-db")
    def init_db():
        """Create all tables."""
        db.create_all()
        click.echo("Tables created.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(name, email, password):
        """Create an admin account from the terminal."""
        from .models import User

        db.create_all()
        if User.query.filter_by(email=email.lower()).first():
            raise click.ClickException("That email already exists.")
        u = User(name=name, email=email.lower())
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Admin {email} created.")

    return app
