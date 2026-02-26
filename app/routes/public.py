import hashlib
import hmac
import logging
from decimal import Decimal

import mercadopago
from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
from flask_login import current_user, login_required

from app.extensions import db, csrf
from app.models import Category, Product, Order, OrderItem
from app.services import InventoryService, PaymentService, TicketService


logger = logging.getLogger(__name__)
public_bp = Blueprint("public", __name__)


# ---------------------------------------------------------------------------
# Carrito (helpers)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Páginas públicas
# ---------------------------------------------------------------------------
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


# Metadata por categoría para el template dinámico
CATEGORY_META = {
    "hamburguesas": {
        "title": "Nuestras",
        "highlight": "Hamburguesas",
        "subtitle": "Carne 100% real, sabor 100% urbano.",
    },
    "snacks": {
        "title": "Snacks",
        "highlight": "Brutales",
        "subtitle": "Para picar o acompañar, pero siempre a lo grande.",
    },
    "postres": {
        "title": "Dulce",
        "highlight": "Final",
        "subtitle": "El antojo que te mereces.",
    },
    "bebidas": {
        "title": "Refresca",
        "highlight": "Tu Sed",
        "subtitle": "Bebidas heladas para bajar la comida.",
    },
    "combos": {
        "title": "Combos",
        "highlight": "Supremos",
        "subtitle": "La experiencia completa al mejor precio.",
    },
}


@public_bp.route("/catalogo/<slug>")
def category(slug: str):
    categories = Category.query.all()
    category_obj = Category.query.filter_by(slug=slug).first_or_404()
    products = Product.query.filter_by(active=True, category_id=category_obj.id).all()
    meta = CATEGORY_META.get(slug, {
        "title": category_obj.name,
        "highlight": "",
        "subtitle": f"Productos de {category_obj.name}.",
    })
    return render_template(
        "public/categoria.html",
        products=products,
        categories=categories,
        active_slug=slug,
        category_title=meta["title"],
        category_highlight=meta["highlight"],
        category_subtitle=meta["subtitle"],
    )


# ---------------------------------------------------------------------------
# Carrito (rutas)
# ---------------------------------------------------------------------------
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
    product = Product.query.get_or_404(product_id)
    if not product.is_available():
        flash("Producto sin stock disponible", "error")
        return redirect(request.referrer or url_for("public.catalog"))
    cart = _get_cart()
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session.modified = True
    flash("Producto agregado al carrito", "success")
    # "Pedir" button sends redirect_to=cart to go straight to cart
    if request.form.get("redirect_to") == "cart":
        return redirect(url_for("public.cart"))
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


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------
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
        user_id=current_user.id,
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

    # Descontar stock para pago en efectivo (se confirma al crear la orden)
    try:
        InventoryService.deduct_stock(order)
    except ValueError as exc:
        logger.warning("Stock insuficiente en orden efectivo #%s: %s", order.id, exc)

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
        user_id=current_user.id,
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

    try:
        preference = PaymentService.create_preference(order.id, mp_items)
    except Exception as exc:
        logger.error("Error al crear preferencia MercadoPago para orden #%s: %s", order.id, exc)
        # Revertir la orden creada para no dejar basura
        db.session.rollback()
        flash(
            "No se pudo procesar el pago con MercadoPago. Intenta con otro método o contacta soporte.",
            "error",
        )
        return redirect(url_for("public.checkout"))

    init_point = preference.get("init_point")
    if not init_point:
        logger.error("MercadoPago no devolvió init_point para orden #%s", order.id)
        db.session.rollback()
        flash("Error al conectar con MercadoPago. Intenta de nuevo.", "error")
        return redirect(url_for("public.checkout"))

    order.mp_preference_id = preference.get("id")
    db.session.commit()
    return redirect(init_point)


# ---------------------------------------------------------------------------
# MercadoPago — Return & Webhook
# ---------------------------------------------------------------------------
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
                session.pop("cart", None)
                flash("Pago aprobado. Tu pedido se registro correctamente.", "success")
                db.session.commit()

                # Descuento idempotente — tolera doble llamada webhook+return
                try:
                    InventoryService.deduct_stock(order)
                except ValueError as exc:
                    logger.warning(
                        "Stock insuficiente en mp_return orden #%s: %s",
                        order.id, exc,
                    )
            else:
                flash("Pago pendiente o rechazado.", "error")
                db.session.commit()
            return redirect(url_for("public.catalog"))
    flash("No se pudo validar el pago.", "error")
    return redirect(url_for("public.catalog"))


def _verify_mp_webhook_signature(request_obj) -> bool:
    """Valida la firma HMAC-SHA256 del webhook de MercadoPago.

    Si ``MP_WEBHOOK_SECRET`` no está configurado, retorna True (modo desarrollo).
    """
    webhook_secret: str = current_app.config.get("MP_WEBHOOK_SECRET", "")
    if not webhook_secret:
        logger.warning(
            "MP_WEBHOOK_SECRET no configurado — webhook sin validar (modo dev)."
        )
        return True

    # MercadoPago envía la firma en el header x-signature
    x_signature = request_obj.headers.get("x-signature", "")
    x_request_id = request_obj.headers.get("x-request-id", "")

    if not x_signature:
        return False

    # Extraer ts y v1 del header  "ts=...,v1=..."
    parts = dict(
        part.split("=", 1) for part in x_signature.split(",") if "=" in part
    )
    ts = parts.get("ts", "")
    received_hash = parts.get("v1", "")

    if not ts or not received_hash:
        return False

    # data_id viene del query string del notification_url o del body
    data = request_obj.json or {}
    data_id = request_obj.args.get("data.id", data.get("data", {}).get("id", ""))

    # Construir el manifest según la spec de MercadoPago
    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
    expected = hmac.new(
        webhook_secret.encode(), manifest.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, received_hash)


@public_bp.route("/mp/webhook", methods=["POST"])
@csrf.exempt
def mp_webhook():
    # Validar firma del webhook
    if not _verify_mp_webhook_signature(request):
        logger.warning("Webhook de MercadoPago rechazado: firma inválida.")
        return {"status": "invalid_signature"}, 403

    data = request.json or {}
    payment_id = data.get("data", {}).get("id")
    access_token = current_app.config.get("MP_ACCESS_TOKEN")

    if payment_id and access_token:
        sdk = mercadopago.SDK(access_token)
        payment_info = sdk.payment().get(payment_id)
        mp_status = payment_info.get("response", {}).get("status")
        external_reference = payment_info.get("response", {}).get("external_reference")

        if external_reference and mp_status == "approved":
            order = Order.query.get(int(external_reference))
            if order:
                order.payment_status = "aprobado"
                order.status = "completado"
                order.mp_payment_id = str(payment_id)
                db.session.commit()

                # Descuento idempotente
                try:
                    InventoryService.deduct_stock(order)
                except ValueError as exc:
                    logger.warning(
                        "Stock insuficiente en webhook orden #%s: %s",
                        order.id, exc,
                    )

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------
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

    # FIX: cargar order y construir message antes de usarlos
    order = Order.query.get_or_404(order_id)
    message = TicketService.build_ticket_message(order, name)

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


# ---------------------------------------------------------------------------
# Contacto
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Perfil de usuario
# ---------------------------------------------------------------------------
@public_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = request.form.get("nombre", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("telefono", "").strip()
        username = request.form.get("username", "").strip()

        if not name or not email:
            flash("Nombre y correo son obligatorios", "error")
            return render_template("public/perfil.html")

        # Verificar email único (si cambió)
        if email != current_user.email:
            from app.models import User as UserModel
            existing = UserModel.query.filter_by(email=email).first()
            if existing:
                flash("Ese correo ya está registrado por otro usuario", "error")
                return render_template("public/perfil.html")

        # Verificar username único (si cambió y no está vacío)
        if username and username != (current_user.username or ""):
            from app.models import User as UserModel
            existing = UserModel.query.filter_by(username=username).first()
            if existing:
                flash("Ese nombre de usuario ya está en uso", "error")
                return render_template("public/perfil.html")

        # Validar teléfono
        if phone and (not phone.isdigit() or len(phone) != 10):
            flash("El teléfono debe tener exactamente 10 dígitos", "error")
            return render_template("public/perfil.html")

        current_user.name = name
        current_user.email = email
        current_user.phone = phone or None
        current_user.username = username or current_user.email
        db.session.commit()
        flash("Perfil actualizado correctamente", "success")

    return render_template("public/perfil.html")

