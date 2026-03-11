from urllib.parse import urlparse
import logging
import re

from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_login import login_user, logout_user, current_user
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from app.extensions import db
from app.models import User
from app.services.ticket_service import EmailService

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

# ── Token constants ──────────────────────────────────────────────────────────
_TOKEN_SALT = "password-reset-v1"
_TOKEN_MAX_AGE = 1800  # 30 minutos


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_next(target: str | None) -> str | None:
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


def _get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _generate_reset_token(email: str) -> str:
    """Genera un token stateless firmado con la SECRET_KEY."""
    return _get_serializer().dumps(email, salt=_TOKEN_SALT)


def _verify_reset_token(token: str) -> str | None:
    """
    Valida el token y retorna el email si es válido.
    Retorna None si expiró (>30 min) o fue manipulado.
    """
    try:
        return _get_serializer().loads(token, salt=_TOKEN_SALT, max_age=_TOKEN_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None


def is_valid_phone(phone: str) -> bool:
    """Checks if phone consists of exactly 10 digits."""
    return bool(re.match(r'^\d{10}$', phone))


def is_valid_username(username: str) -> bool:
    """Checks if username contains only alphanumeric characters, underscores or hyphens."""
    if '@' in username:
        return True
    return bool(re.match(r'^[a-zA-Z0-9_\-]+$', username))


# ── Login ────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("public.home"))

    next_url = _safe_next(request.args.get("next"))

    if request.method == "POST":
        username = request.form.get("usuario", "").strip()
        password = request.form.get("contrasena", "")
        next_url = _safe_next(request.form.get("next") or request.args.get("next"))

        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()
        if not user or not user.check_password(password):
            flash("Credenciales inválidas", "error")
        else:
            login_user(user, remember=user.is_admin)
            if user.is_admin:
                return redirect(url_for("admin.dashboard"))
            if next_url:
                return redirect(next_url)
            return redirect(url_for("public.home"))

    return render_template("login.html", next=next_url)


# ── Register ─────────────────────────────────────────────────────────────────

@auth_bp.route("/registro", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("nombre", "").strip()
        email = request.form.get("correo", "").strip()
        phone = request.form.get("telefono", "").strip()
        password = request.form.get("contrasena", "")
        username = request.form.get("usuario", email).strip() or email

        if not name or not email or not password:
            flash("Completa todos los campos obligatorios", "error")
            return render_template("registro-usuarios.html")

        if phone and not is_valid_phone(phone):
            flash("El número de teléfono debe tener exactamente 10 dígitos.", "error")
            return render_template("registro-usuarios.html")

        if not is_valid_username(username):
            flash("El nombre de usuario contiene caracteres no permitidos", "error")
            return render_template("registro-usuarios.html")

        if User.query.filter_by(email=email).first():
            flash("El correo ya está registrado", "error")
            return render_template("registro-usuarios.html")

        if username and username != email and User.query.filter_by(username=username).first():
            flash("El nombre de usuario ya está en uso", "error")
            return render_template("registro-usuarios.html")

        user = User(name=name, email=email, phone=phone, username=username, is_admin=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Registro exitoso. Ahora puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("registro-usuarios.html")


# ── Logout ───────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
def logout():
    logout_user()
    flash("Has cerrado sesión exitosamente", "success")
    return redirect(url_for("auth.login"))


# ── Admin Login ──────────────────────────────────────────────────────────────

@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("public.home"))

    if request.method == "POST":
        username = request.form.get("usuario", "").strip()
        password = request.form.get("contrasena", "")

        if not username or not password:
            flash("Credenciales requeridas", "error")
            return render_template("login-admin.html")

        user = User.query.filter_by(username=username, is_admin=True).first()
        if not user or not user.check_password(password):
            flash("Credenciales inválidas", "error")
        else:
            login_user(user, remember=True)
            return redirect(url_for("admin.dashboard"))

    return render_template("login-admin.html")


# ── Forgot Password ─────────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """
    Genera un token de reset y envía el correo.
    Anti User-Enumeration: responde con mensaje genérico
    independientemente de si el email existe o no.
    """
    if current_user.is_authenticated:
        return redirect(url_for("public.home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if email:
            user = User.query.filter_by(email=email).first()
            if user:
                token = _generate_reset_token(user.email)
                reset_url = url_for("auth.reset_password", token=token, _external=True)

                body_text = (
                    f"Hola {user.name},\n\n"
                    f"Recibimos una solicitud para restablecer tu contraseña "
                    f"en Duncan Dhu.\n\n"
                    f"Haz clic en el siguiente enlace para crear una nueva "
                    f"contraseña (válido por 30 minutos):\n\n"
                    f"{reset_url}\n\n"
                    f"Si tú no solicitaste este cambio, ignora este correo.\n\n"
                    f"— Equipo Duncan Dhu 🍔"
                )

                body_html = (
                    f"<div style='font-family:Arial,sans-serif;max-width:480px;"
                    f"margin:0 auto;background:#121212;color:#fff;padding:24px;"
                    f"border:2px solid #FFDD00;'>"
                    f"<h2 style='color:#FFDD00;margin:0 0 16px;'>Duncan Dhu</h2>"
                    f"<p>Hola <strong>{user.name}</strong>,</p>"
                    f"<p>Recibimos una solicitud para restablecer tu contraseña.</p>"
                    f"<p style='text-align:center;margin:24px 0;'>"
                    f"<a href='{reset_url}' style='display:inline-block;"
                    f"background:#FFDD00;color:#000;padding:12px 32px;"
                    f"text-decoration:none;font-weight:bold;"
                    f"text-transform:uppercase;'>Restablecer Contraseña</a></p>"
                    f"<p style='color:#999;font-size:12px;'>Este enlace expira "
                    f"en 30 minutos. Si no solicitaste este cambio, ignora "
                    f"este correo.</p></div>"
                )

                sent = EmailService.send(
                    user.email,
                    "Restablecer contraseña — Duncan Dhu",
                    body_text,
                    body_html,
                )
                if not sent:
                    logger.warning(
                        "No se pudo enviar correo de reset (SMTP no disponible)"
                    )

        # Respuesta genérica (anti user-enumeration)
        flash(
            "Si el correo está registrado, recibirás instrucciones "
            "para restablecer tu contraseña.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


# ── Reset Password ───────────────────────────────────────────────────────────

@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    """
    Valida el token firmado y permite establecer nueva contraseña.
    Token stateless vía itsdangerous con max_age=1800s.
    """
    if current_user.is_authenticated:
        return redirect(url_for("public.home"))

    email = _verify_reset_token(token)
    if email is None:
        flash(
            "El enlace ha expirado o es inválido. Solicita uno nuevo.",
            "error",
        )
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm_password", "").strip()

        if not password or len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres", "error")
            return render_template("auth/reset_password.html", token=token)

        if password != confirm:
            flash("Las contraseñas no coinciden", "error")
            return render_template("auth/reset_password.html", token=token)

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Error al restablecer la contraseña", "error")
            return redirect(url_for("auth.forgot_password"))

        user.set_password(password)
        db.session.commit()

        # Notificar al usuario del cambio
        EmailService.send(
            user.email,
            "Contraseña actualizada — Duncan Dhu",
            (
                f"Hola {user.name},\n\n"
                f"Tu contraseña ha sido restablecida exitosamente.\n\n"
                f"Si tú no realizaste este cambio, contacta a soporte "
                f"de inmediato.\n\n"
                f"— Equipo Duncan Dhu 🍔"
            ),
        )

        flash("Contraseña restablecida exitosamente. Inicia sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)
