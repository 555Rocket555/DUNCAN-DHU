import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://admin:12345@localhost:5432/duncan_dhu",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "")
    MP_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY", "")
    MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")

    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@duncandhu.local")

    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")

    SOCIAL_FACEBOOK = os.getenv("SOCIAL_FACEBOOK", "https://www.facebook.com/")
    SOCIAL_INSTAGRAM = os.getenv("SOCIAL_INSTAGRAM", "https://www.instagram.com/")
    SOCIAL_TIKTOK = os.getenv("SOCIAL_TIKTOK", "https://www.tiktok.com/")
    GOOGLE_MAPS_URL = os.getenv("GOOGLE_MAPS_URL", "https://maps.google.com/")

    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
