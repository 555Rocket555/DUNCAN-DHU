from decimal import Decimal

import mercadopago
from flask import Blueprint, current_app, render_template, request, redirect, url_for, session, flash
from flask_login import current_user

from app.extensions import db
from app.models import Category, Product, Order, OrderItem
from app.services import PaymentService, TicketService


public_bp = Blueprint("public", __name__)


def _get_cart():
    return session.setdefault("cart", {})


def _cart_items():
    cart = _get_cart()
    items = []
    total = Decimal("0")
    for product_id, qty in cart.items():
        product = Product.query.get(int(product_id))
        if not product:
            continue
        price = Decimal(str(product.price))
        quantity = int(qty)
        line_total = price * quantity
        items.append(
            {
                "product": product,
                "quantity": quantity,
                "line_total": line_total,
            }
        )
        total += line_total
    return items, total


@public_bp.route("/")
def home():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin.dashboard"))
    popular_products = Product.query.filter_by(active=True).limit(4).all()
    categories = Category.query.all()
    return render_template(
        "Principal.html",
        popular_products=popular_products,
        categories=categories,
        social={
            "facebook": current_app.config.get("SOCIAL_FACEBOOK"),
            "instagram": current_app.config.get("SOCIAL_INSTAGRAM"),
            "tiktok": current_app.config.get("SOCIAL_TIKTOK"),
        },
        maps_url=current_app.config.get("GOOGLE_MAPS_URL"),
    )


@public_bp.route("/catalogo")
def catalog():
    products = Product.query.filter_by(active=True).all()
    categories = Category.query.all()
    return render_template(
        "productos-usuarios.html",
        products=products,
        categories=categories,
        active_slug="todos",
    )


@public_bp.route("/catalogo/<slug>")
def category(slug: str):
    categories = Category.query.all()
    category_obj = Category.query.filter_by(slug=slug).first_or_404()
    products = Product.query.filter_by(active=True, category_id=category_obj.id).all()
    template_map = {
        "hamburguesas": "U-hamburguesas.html",
        "snacks": "u-snacks.html",
        "postres": "u-postres.html",
        "bebidas": "u-bebidas.html",
        "combos": "u-combos.html",
    }
    template_name = template_map.get(slug, "productos-usuarios.html")
    return render_template(
        template_name,
        products=products,
        categories=categories,
        active_slug=slug,
    )


@public_bp.route("/carrito")
def cart():
    items, total = _cart_items()
    return render_template(
        "carrito de compras-usuarios.html",
        cart_items=items,
        total=total,
    )


@public_bp.route("/carrito/agregar/<int:product_id>", methods=["POST"])
def add_to_cart(product_id: int):
    cart = _get_cart()
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session.modified = True
    flash("Producto agregado al carrito", "success")
    return redirect(request.referrer or url_for("public.catalog"))


@public_bp.route("/carrito/actualizar", methods=["POST"])
def update_cart():
    product_id = request.form.get("product_id")
    action = request.form.get("action")
    cart = _get_cart()
    if product_id in cart:
        qty = int(cart[product_id])
        if action == "plus":
            qty += 1
        elif action == "minus":
            qty -= 1
        if qty <= 0:
            cart.pop(product_id, None)
        else:
            cart[product_id] = qty
        session.modified = True
    return redirect(url_for("public.cart"))


@public_bp.route("/checkout")
def checkout():
    items, total = _cart_items()
    if not items:
        flash("Tu carrito está vacío", "error")
        return redirect(url_for("public.catalog"))
    if not current_user.is_authenticated:
        flash("Inicia sesión para continuar con el pago", "error")
        return redirect(url_for("auth.login", next=url_for("public.checkout")))
    return render_template(
        "método de pago-usuarios.html",
        cart_items=items,
        total=total,
    )


@public_bp.route("/checkout/efectivo", methods=["POST", "GET"])
def checkout_cash():
    items, total = _cart_items()
    if not items:
        return redirect(url_for("public.catalog"))
    if not current_user.is_authenticated:
        flash("Inicia sesión para continuar con el pago", "error")
        return redirect(url_for("auth.login", next=url_for("public.checkout")))

    order = Order(
        user_id=current_user.id if current_user.is_authenticated else None,
        status="pendiente",
        payment_method="efectivo",
        payment_status="pendiente",
        total=total,
    )
    db.session.add(order)
    db.session.flush()

    for item in items:
        db.session.add(
            OrderItem(
                order_id=order.id,
                product_id=item["product"].id,
                name=item["product"].name,
                price=item["product"].price,
                quantity=item["quantity"],
            )
        )

    db.session.commit()
    # session.pop("cart", None)  <-- Keep cart until confirmed
    return render_template("efectivo-usuario.html", order=order, sent=False)


@public_bp.route("/checkout/mercadopago", methods=["POST"])
def checkout_mp():
    items, total = _cart_items()
    if not items:
        return redirect(url_for("public.catalog"))
    if not current_user.is_authenticated:
        flash("Inicia sesión para continuar con el pago", "error")
        return redirect(url_for("auth.login", next=url_for("public.checkout")))

    order = Order(
        user_id=current_user.id if current_user.is_authenticated else None,
        status="pendiente",
        payment_method="mercadopago",
        payment_status="pendiente",
        total=total,
    )
    db.session.add(order)
    db.session.flush()

    mp_items = []
    for item in items:
        db.session.add(
            OrderItem(
                order_id=order.id,
                product_id=item["product"].id,
                name=item["product"].name,
                price=item["product"].price,
                quantity=item["quantity"],
            )
        )
        mp_items.append(
            {
                "title": item["product"].name,
                "quantity": item["quantity"],
                "currency_id": "MXN",
                "unit_price": float(item["product"].price),
            }
        )

    db.session.commit()

    preference = PaymentService.create_preference(order.id, mp_items)
    order.mp_preference_id = preference.get("id")
    db.session.commit()
    # session.pop("cart", None) <-- Keep cart until confirmed
    return redirect(preference.get("init_point"))


@public_bp.route("/mp/return")
def mp_return():
    status = request.args.get("status", "pending")
    external_reference = request.args.get("external_reference")
    if external_reference:
        order = Order.query.get(int(external_reference))
        if order:
            order.payment_status = "aprobado" if status == "success" else status
            if status == "success":
                order.status = "completado"
                session.pop("cart", None) # Clear cart only on success
                flash("Pago aprobado. Tu pedido se registro correctamente.", "success")
            else:
                flash("Pago pendiente o rechazado.", "error")
            db.session.commit()
            return redirect(url_for("public.catalog"))
    flash("No se pudo validar el pago.", "error")
    return redirect(url_for("public.catalog"))


@public_bp.route("/mp/webhook", methods=["POST"])
def mp_webhook():
    data = request.json or {}
    payment_id = data.get("data", {}).get("id")
    access_token = current_app.config.get("MP_ACCESS_TOKEN")
    if payment_id and access_token:
        sdk = mercadopago.SDK(access_token)
        payment_info = sdk.payment().get(payment_id)
        external_reference = payment_info.get("response", {}).get("external_reference")
        if external_reference:
            order = Order.query.get(int(external_reference))
            if order:
                order.payment_status = "aprobado"
                order.status = "completado"
                order.mp_payment_id = str(payment_id)
                db.session.commit()
    return {"status": "ok"}


@public_bp.route("/ticket/<int:order_id>")
def ticket_view(order_id: int):
    order = Order.query.get_or_404(order_id)
    return render_template("ticket-tarjeta.html", order=order)


@public_bp.route("/ticket/enviar", methods=["POST"])
def ticket_send():
    order_id = request.form.get("order_id")
    channel = request.form.get("channel")
    name = request.form.get("nombre", "").strip()
    whatsapp = request.form.get("whatsapp", "").strip()
    email = request.form.get("correo", "").strip()
    try:
        if channel == "whatsapp":
            if not whatsapp:
                flash("Ingresa un numero de WhatsApp valido", "error")
                return render_template("efectivo-usuario.html", order=order, sent=False)
            TicketService.send_whatsapp(whatsapp, message)
        elif channel == "correo":
            if not email:
                flash("Ingresa un correo valido", "error")
                return render_template("efectivo-usuario.html", order=order, sent=False)
            TicketService.send_email(email, "Tu ticket Duncan Dhu", message)
        else:
            flash("Selecciona un metodo de envio", "error")
            return render_template("efectivo-usuario.html", order=order, sent=False)
    except RuntimeError as exc:
        flash(str(exc), "error")
        return render_template("efectivo-usuario.html", order=order, sent=False)

    flash("Se envio el ticket correctamente", "success")
    return render_template("efectivo-usuario.html", order=order, sent=True)


@public_bp.route("/contactanos", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        flash(
            "Se ha enviado correctamente, atenderemos tu solicitud lo mas pronto posible",
            "success",
        )
        return redirect(url_for("public.contact"))
    return render_template(
        "contactanos.html",
        social={
            "facebook": current_app.config.get("SOCIAL_FACEBOOK"),
            "instagram": current_app.config.get("SOCIAL_INSTAGRAM"),
            "tiktok": current_app.config.get("SOCIAL_TIKTOK"),
            "maps": current_app.config.get("GOOGLE_MAPS_URL"),
        },
    )

