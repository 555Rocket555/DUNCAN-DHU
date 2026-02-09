import os

from flask import Flask
from dotenv import load_dotenv

from app.config import Config
from app.extensions import db, migrate, login_manager
from app.models import User, seed_defaults
from app.routes.public import public_bp
from app.routes.auth import auth_bp
from app.routes.admin import admin_bp
from app.routes.api import api_bp


load_dotenv()


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

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        seed_defaults(app.config.get("ADMIN_USERNAME"), app.config.get("ADMIN_PASSWORD"))

    return app


app = create_app()
