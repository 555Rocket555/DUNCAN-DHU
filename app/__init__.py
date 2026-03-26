import os
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from flask_login import current_user, logout_user

# Cargar .env ANTES de importar Config, que ahora exige SECRET_KEY y DATABASE_URL.
load_dotenv()

from flask import Flask  # noqa: E402

from app.config import Config  # noqa: E402
from app.extensions import db, migrate, login_manager, csrf  # noqa: E402
from app.models import User, seed_defaults, seed_extended, seed_recipes  # noqa: E402
from app.routes.public import public_bp  # noqa: E402
from app.routes.auth import auth_bp  # noqa: E402
from app.routes.admin import admin_bp  # noqa: E402
from app.routes.api import api_bp  # noqa: E402


def create_app():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
        static_url_path="/static",
    )
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    csrf.init_app(app)

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    from flask import flash, redirect, session, url_for  # noqa: F401 – runtime import inside factory

    _SESSION_TIMEOUT = timedelta(minutes=60)

    @app.before_request
    def enforce_session_timeout():
        """
        Cierra la sesión del usuario si lleva más de 60 min sin actividad.
        Se ejecuta antes de CADA petición autenticada.
        """
        if current_user.is_authenticated:
            last = session.get("last_active")
            now = datetime.now(timezone.utc)
            if last:
                # last puede llegar como string ISO si el serializer de Flask lo convirtió
                if isinstance(last, str):
                    try:
                        last = datetime.fromisoformat(last)
                    except ValueError:
                        last = None
                if last and (now - last) > _SESSION_TIMEOUT:
                    logout_user()
                    session.clear()
                    flash("Tu sesión ha expirado por inactividad. Por favor, inicia sesión nuevamente.", "warning")
                    return redirect(url_for("auth.login"))
            session["last_active"] = now.isoformat()

    @app.after_request
    def add_no_cache_headers(response):
        if current_user.is_authenticated:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        seed_defaults(app.config.get("ADMIN_USERNAME"), app.config.get("ADMIN_PASSWORD"))

    @app.cli.command("seed-recipes")
    def cli_seed_recipes():
        """Populate product_recipes with default seed data."""
        seed_recipes()
        print("✅ Seed de recetas completado.")

    @app.cli.command("seed-extended")
    def cli_seed_extended():
        """Add gourmet extended products to the catalog."""
        seed_extended()
        print("✅ Catálogo gourmet extendido completado.")

    return app
