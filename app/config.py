import os
from datetime import timedelta

import cloudinary


class Config:
    # ── Seguridad ──────────────────────────────────────────────────────────
    # SECRET_KEY y DATABASE_URL son OBLIGATORIOS vía .env.
    # La app no arrancará sin ellos, evitando valores inseguros por defecto.
    SECRET_KEY = os.environ["SECRET_KEY"]

    _raw_db_url = os.environ["DATABASE_URL"]
    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif _raw_db_url.startswith("postgresql://") and "+psycopg" not in _raw_db_url:
        _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    REMEMBER_COOKIE_REFRESH_EACH_REQUEST = True

    # ── MercadoPago ────────────────────────────────────────────────────────
    MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")
    MP_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY", "")
    MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")

    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

    # ── Cloudinary ─────────────────────────────────────────────────────────
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "ddxqkjdnp")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "661358564123437")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

    # ── Email / SMTP ──────────────────────────────────────────────────────
    SMTP_HOST = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = (
        os.getenv("SMTP_FROM")
        or os.getenv("MAIL_DEFAULT_SENDER", "no-reply@duncandhu.local")
    )

    # ── Twilio / WhatsApp ─────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")

    # ── Redes Sociales / Maps ─────────────────────────────────────────────
    SOCIAL_FACEBOOK = os.getenv("SOCIAL_FACEBOOK", "https://www.facebook.com/")
    SOCIAL_INSTAGRAM = os.getenv("SOCIAL_INSTAGRAM", "https://www.instagram.com/")
    SOCIAL_TIKTOK = os.getenv("SOCIAL_TIKTOK", "https://www.tiktok.com/")
    GOOGLE_MAPS_URL = os.getenv(
        "GOOGLE_MAPS_URL",
        "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3762.661642921577"
        "!2d-99.16869368509337!3d19.42702448688752!2m3!1f0!2f0!3f0!3m2!1i1024"
        "!2i768!4f13.1!3m3!1m2!1s0x85d1ff35f5bd1563%3A0x6c366f0e2de02ff7"
        "!2sEl%20%C3%81ngel%20de%20la%20Independencia!5e0!3m2!1ses-419!2smx"
        "!4v1621234567890!5m2!1ses-419!2smx",
    )

    # ── Admin seed ────────────────────────────────────────────────────────
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


# ── Inicialización global de Cloudinary ───────────────────────────────────
cloudinary.config(
    cloud_name=Config.CLOUDINARY_CLOUD_NAME,
    api_key=Config.CLOUDINARY_API_KEY,
    api_secret=Config.CLOUDINARY_API_SECRET,
    secure=True,
)
