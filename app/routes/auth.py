from urllib.parse import urlparse
import re

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from app.extensions import db
from app.models import User


auth_bp = Blueprint("auth", __name__)


def _safe_next(target: str | None) -> str | None:
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


def is_valid_phone(phone: str) -> bool:
    """Checks if phone consists of exactly 10 digits."""
    return bool(re.match(r'^\d{10}$', phone))


def is_valid_username(username: str) -> bool:
    """Checks if username contains only alphanumeric characters, underscores or hyphens."""
    # This also helps prevent simple SQL injection if parameter binding wasn't used (though SQLAlchemy handles it)
    if '@' in username: # Allow email as username
        return True
    return bool(re.match(r'^[a-zA-Z0-9_\-]+$', username))


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
        
        # SQLAlchemy handles parameter binding, so standard SQL injection is mitigated.
        # But we still validate basic inputs.
        user = User.query.filter((User.username == username) | (User.email == username)).first()
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


@auth_bp.route("/registro", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("nombre", "").strip()
        email = request.form.get("correo", "").strip()
        phone = request.form.get("telefono", "").strip()
        password = request.form.get("contrasena", "")
        username = request.form.get("usuario", email).strip() or email # Default to email if empty

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

        # Check if username exists if it's different from email
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


@auth_bp.route("/logout")
def logout():
    logout_user()
    flash("Has cerrado sesión exitosamente", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("public.home"))

    if request.method == "POST":
        username = request.form.get("usuario", "").strip()
        password = request.form.get("contrasena", "")
        
        # Sanitize input slightly just in case
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
