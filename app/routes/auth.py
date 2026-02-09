from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from app.extensions import db
from app.models import User


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("public.home"))

    if request.method == "POST":
        username = request.form.get("usuario", "").strip()
        password = request.form.get("contrasena", "")
        user = User.query.filter((User.username == username) | (User.email == username)).first()
        if not user or not user.check_password(password):
            flash("Credenciales inválidas", "error")
        else:
            login_user(user)
            return redirect(url_for("public.home"))

    return render_template("login.html")


@auth_bp.route("/registro", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("nombre", "").strip()
        email = request.form.get("correo", "").strip()
        phone = request.form.get("telefono", "").strip()
        password = request.form.get("contrasena", "")
        username = request.form.get("usuario", email)

        if not name or not email or not password:
            flash("Completa todos los campos obligatorios", "error")
            return render_template("registro-usuarios.html")

        if User.query.filter_by(email=email).first():
            flash("El correo ya está registrado", "error")
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
    return redirect(url_for("public.home"))


@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("usuario", "").strip()
        password = request.form.get("contrasena", "")
        user = User.query.filter_by(username=username, is_admin=True).first()
        if not user or not user.check_password(password):
            flash("Credenciales inválidas", "error")
        else:
            login_user(user)
            return redirect(url_for("admin.dashboard"))

    return render_template("login-admin.html")
