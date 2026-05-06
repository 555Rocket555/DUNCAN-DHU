import random
from datetime import datetime, timezone
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
    session,
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
_TOKEN_EMAIL_SALT = "email-verify-v1"
_TOKEN_MAX_AGE = 1800  # 30 minutos
_TOKEN_EMAIL_MAX_AGE = 86400  # 24 horas para verificación de email


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


def _generate_email_verify_token(email: str) -> str:
    """Genera un token stateless firmado para verificación de email."""
    return _get_serializer().dumps(email, salt=_TOKEN_EMAIL_SALT)


def _verify_email_token(token: str) -> str | None:
    """
    Valida el token de verificación de email y retorna el email si es válido.
    Retorna None si expiró (>24 horas) o fue manipulado.
    """
    try:
        return _get_serializer().loads(token, salt=_TOKEN_EMAIL_SALT, max_age=_TOKEN_EMAIL_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None


def _verify_recaptcha(recaptcha_response: str) -> bool:
    """
    Verifica el token de reCAPTCHA v2 con Google.
    Retorna True si es válido, False en caso contrario.
    """
    print(f"DEBUG: reCAPTCHA response: '{recaptcha_response}'")  # Debug
    if not recaptcha_response:
        print("DEBUG: No reCAPTCHA response provided")  # Debug
        return False

    import requests

    secret_key = current_app.config.get("RECAPTCHA_SECRET_KEY", "6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe")  # Test key
    print(f"DEBUG: Using secret key: {secret_key[:10]}...")  # Debug
    verify_url = "https://www.google.com/recaptcha/api/siteverify"

    try:
        response = requests.post(verify_url, data={
            "secret": secret_key,
            "response": recaptcha_response
        }, timeout=10)

        result = response.json()
        print(f"DEBUG: reCAPTCHA API response: {result}")  # Debug
        return result.get("success", False)
    except Exception as e:
        print(f"DEBUG: Error verifying reCAPTCHA: {e}")  # Debug
        logger.error("Error verificando reCAPTCHA: %s", e)
        return False


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
        recaptcha_response = request.form.get("g-recaptcha-response", "")
        next_url = _safe_next(request.form.get("next") or request.args.get("next"))

        # ── Verificar reCAPTCHA ────────────────────────────────────────
        if not _verify_recaptcha(recaptcha_response):
            flash("Por favor verifica que no eres un robot.", "warning")
            return render_template("login.html")

        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()

        if not user or not user.check_password(password):
            flash("Credenciales inválidas", "error")

        # ── Usuario normal: verificar email antes de login ──────────────
        elif not user.is_admin and not user.email_verified:
            flash("Por favor verifica tu correo electrónico antes de iniciar sesión.", "error")
            return render_template("auth/email_verification_pending.html", email=user.email)

        # ── Administrador: flujo MFA ──────────────────────────────────
        elif user.is_admin:
            otp = str(random.randint(100000, 999999))
            session["mfa_code"]    = otp
            session["mfa_user_id"] = user.id

            # DEBUG: Mostrar el código MFA en la consola del servidor para pruebas.
            print(f"DEBUG: Código MFA para admin '{user.username}': {otp}")

            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            body_html = f"""
            <div style="font-family:sans-serif;max-width:480px;margin:auto;">
              <h2 style="color:#f5a623;">&#128274; Código de Acceso Admin</h2>
              <p>Hola, <strong>{user.name}</strong>.</p>
              <p>Tu código de verificación de un solo uso es:</p>
              <div style="font-size:2.5rem;font-weight:bold;letter-spacing:.4em;
                          background:#1a1a1a;color:#f5a623;padding:16px 24px;
                          border-radius:8px;text-align:center;margin:16px 0;">
                {otp}
              </div>
              <p style="color:#888;">Válido por 10 minutos &middot; {now_str}</p>
              <p>Si no intentaste iniciar sesión, cambia tu contraseña de inmediato.</p>
            </div>
            """
            EmailService.send(
                to_email=user.email,
                subject="Código de Acceso Admin — Duncan Dhu",
                body_text=f"Tu código de acceso es: {otp} (válido 10 min)",
                body_html=body_html,
            )
            flash("Te enviamos un código de 6 dígitos a tu correo.", "info")
            return redirect(url_for("auth.mfa_verify"))

        # ── Cliente normal: login + alerta por correo ────────────────────
        else:
            login_user(user, remember=False)
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            body_html = f"""
            <div style="font-family:sans-serif;max-width:480px;margin:auto;">
              <h2 style="color:#f5a623;">&#128275; Nuevo inicio de sesión</h2>
              <p>Hola, <strong>{user.name}</strong>.</p>
              <p>Detectamos un nuevo inicio de sesión en tu cuenta de
                 <strong>Duncan Dhu</strong>.</p>
              <table style="background:#1a1a1a;border-radius:8px;padding:16px;width:100%;">
                <tr><td style="color:#888;">Fecha y hora</td>
                    <td style="color:#fff;">{now_str}</td></tr>
              </table>
              <p style="color:#888;margin-top:12px;">Si no fuiste tú, cambia tu
                 contraseña inmediatamente desde tu perfil.</p>
            </div>
            """
            EmailService.send(
                to_email=user.email,
                subject="Nuevo inicio de sesión detectado en Duncan Dhu",
                body_text=f"Nuevo inicio de sesión en tu cuenta el {now_str}.",
                body_html=body_html,
            )
            if next_url:
                return redirect(next_url)
            return redirect(url_for("public.home"))

    return render_template("login.html", next=next_url)


# ── MFA Verify (Admin) ────────────────────────────────────────────

@auth_bp.route("/mfa-verify", methods=["GET", "POST"])
def mfa_verify():
    """Verifica el OTP de 6 dígitos enviado al email del administrador."""
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    # Protección: si no hay código en sesión, mandar al login
    if "mfa_code" not in session or "mfa_user_id" not in session:
        flash("Sesión de verificación inválida. Por favor, inicia sesión de nuevo.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        ingresado = request.form.get("otp_code", "").strip()

        if ingresado == session.get("mfa_code"):
            user = User.query.get(session.pop("mfa_user_id"))
            session.pop("mfa_code", None)

            if not user or not user.is_admin:
                flash("Error de verificación. Intenta de nuevo.", "error")
                return redirect(url_for("auth.login"))

            login_user(user, remember=False)
            flash(f"Bienvenido, {user.name}. Acceso admin verificado. ✅", "success")
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Código incorrecto. Verifica tu correo e intenta de nuevo.", "error")

    return render_template("auth/mfa_verify.html")



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

        if not request.form.get("terminos"):
            flash("Debes aceptar los términos y condiciones", "error")
            return render_template("registro-usuarios.html")

        if not request.form.get("mayor_edad"):
            flash("Debes confirmar que eres mayor de edad", "error")
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

        user = User(name=name, email=email, phone=phone, username=username, is_admin=False, email_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # Generar token de verificación y enviar correo
        verify_token = _generate_email_verify_token(user.email)
        verify_url = url_for("auth.verify_email", token=verify_token, _external=True)

        try:
            body_text = f"Hola {user.name},\n\n¡Bienvenido a Duncan Dhu! Por favor verifica tu correo haciendo clic en el siguiente enlace:\n\n{verify_url}\n\nEste enlace expirará en 24 horas.\n\nSi no creaste esta cuenta, ignora este correo.\n\n— Equipo Duncan Dhu 🍔"
            body_html = f"""
            <div style="font-family:sans-serif;max-width:480px;margin:auto;">
              <h2 style="color:#FFDD00;">¡Bienvenido a Duncan Dhu, {user.name}!</h2>
              <p>Por favor verifica tu correo electrónico haciendo clic en el botón de abajo:</p>
              <div style="text-align:center;margin:24px 0;">
                <a href="{verify_url}" style="display:inline-block;background:#FFDD00;color:#000;padding:12px 24px;text-decoration:none;font-weight:bold;border-radius:4px;">Verificar Correo</a>
              </div>
              <p style="color:#888;font-size:12px;">O copia este enlace: <br/>{verify_url}</p>
              <p style="color:#888;font-size:12px;">Este enlace expirará en 24 horas.</p>
              <p style="color:#888;font-size:12px;">Si no creaste esta cuenta, ignora este correo.</p>
            </div>
            """
            EmailService.send(user.email, "Verifica tu correo - Duncan Dhu", body_text, body_html)
        except Exception as e:
            logger.error("Error enviando email de verificación: %s", e)

        flash("Cuenta creada exitosamente. Te hemos enviado un correo con un enlace de verificación. Por favor verifica tu correo para activar tu cuenta.", "success")
        return redirect(url_for("auth.email_verification_pending", email=user.email))

    return render_template("registro-usuarios.html")


# ── Logout ───────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
def logout():
    logout_user()
    session.pop("_user_id", None)
    session.pop("_remember", None)
    session.pop("_fresh", None)
    session.pop("last_active", None)
    session.clear()
    session.modified = True
    flash("Has cerrado sesión exitosamente", "success")

    response = redirect(url_for("auth.login"))
    response.delete_cookie(current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token"), path="/")
    return response


# ── Email Verification ──────────────────────────────────────────────────────

@auth_bp.route("/verificar-correo", methods=["GET", "POST"])
def verify_email():
    """Verifica el correo del usuario mediante token."""
    token = request.args.get("token")
    if not token:
        flash("Enlace de verificación inválido o expirado", "error")
        return redirect(url_for("auth.login"))

    email = _verify_email_token(token)
    if not email:
        flash("Enlace de verificación expirado. Por favor solicita uno nuevo.", "error")
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Usuario no encontrado", "error")
        return redirect(url_for("auth.login"))

    if user.email_verified:
        flash("Tu correo ya ha sido verificado. Puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    # Marcar email como verificado
    user.email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    db.session.commit()

    flash("¡Correo verificado exitosamente! Ahora puedes iniciar sesión.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/verificacion-pendiente")
def email_verification_pending():
    """Muestra página de espera mientras el usuario verifica su correo."""
    email = request.args.get("email", "")
    return render_template("auth/email_verification_pending.html", email=email)


@auth_bp.route("/reenviar-verificacion", methods=["POST"])
def resend_verification_email():
    """Reenvía el email de verificación."""
    email = request.form.get("email", "").strip()
    if not email:
        flash("Por favor proporciona tu correo", "error")
        return redirect(url_for("auth.email_verification_pending", email=email))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Correo no encontrado", "error")
        return redirect(url_for("auth.email_verification_pending", email=email))

    if user.email_verified:
        flash("Tu correo ya ha sido verificado. Puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    # Generar nuevo token y reenviar
    verify_token = _generate_email_verify_token(user.email)
    verify_url = url_for("auth.verify_email", token=verify_token, _external=True)

    try:
        body_text = f"Hola {user.name},\n\nAquí está el enlace de verificación de tu correo:\n\n{verify_url}\n\nEste enlace expirará en 24 horas.\n\n— Equipo Duncan Dhu 🍔"
        body_html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;">
          <h2 style="color:#FFDD00;">Verifica tu correo</h2>
          <p>Hola {user.name},</p>
          <p>Aquí está el enlace para verificar tu correo:</p>
          <div style="text-align:center;margin:24px 0;">
            <a href="{verify_url}" style="display:inline-block;background:#FFDD00;color:#000;padding:12px 24px;text-decoration:none;font-weight:bold;border-radius:4px;">Verificar Correo</a>
          </div>
          <p style="color:#888;font-size:12px;">Este enlace expirará en 24 horas.</p>
        </div>
        """
        EmailService.send(user.email, "Verifica tu correo - Duncan Dhu", body_text, body_html)
        flash("Te hemos reenviado el enlace de verificación. Por favor revisa tu correo.", "success")
    except Exception as e:
        logger.error("Error reenviando email de verificación: %s", e)
        flash("Error al reenviar el correo. Por favor intenta más tarde.", "error")

    return redirect(url_for("auth.email_verification_pending", email=email))


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
            login_user(user, remember=False)
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
