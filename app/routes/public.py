import hashlib
import hmac
import logging
from decimal import Decimal

import mercadopago
from flask import (
    Blueprint,
    current_app,
    jsonify,
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
        "carrito-compras-usuarios.html",
        cart_items=items,
        total=total,
    )


@public_bp.route("/carrito/agregar/<int:product_id>", methods=["POST"])
def add_to_cart(product_id: int):
    # Strict AJAX detection: only the header our JS explicitly sets
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    product = Product.query.get(product_id)
    if product is None:
        if is_ajax:
            return jsonify(success=False, message="Producto no encontrado"), 404
        flash("Producto no encontrado", "error")
        return redirect(request.referrer or url_for("public.catalog"))

    if not product.is_available():
        if is_ajax:
            return jsonify(success=False, message="Producto sin stock disponible"), 409
        flash("Producto sin stock disponible", "error")
        return redirect(request.referrer or url_for("public.catalog"))

    cart = _get_cart()
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session.modified = True
    cart_total = sum(int(v) for v in cart.values())

    if is_ajax:
        return jsonify(
            success=True,
            message=f"{product.name} agregado al carrito",
            cart_total_items=cart_total,
        )

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


@public_bp.route("/carrito/eliminar", methods=["POST"])
def remove_from_cart():
    product_id = request.form.get("product_id")
    cart = _get_cart()
    cart.pop(str(product_id), None)
    session.modified = True
    flash("Producto eliminado del carrito", "success")
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
        "metodo-pago-usuarios.html",
        cart_items=items,
        total=total,
    )


@public_bp.route("/checkout/efectivo", methods=["POST"])
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

    # Correo de Creación de Orden (Efectivo)
    try:
        user_email = current_user.email
        body = f"Hola {current_user.name},\n\nHemos recibido tu pedido #{order.id} por un total de ${order.total:.2f}. Tu pedido se pagará en efectivo a la entrega y está actualmente en estado '{order.status}'.\n\n— Equipo Duncan Dhu 🍔"
        TicketService.send_email(user_email, f"Confirmación de Pedido #{order.id} — Duncan Dhu", body)
    except Exception as e:
        logger.error("Error enviando email confirmacion efectivo: %s", e)

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

    # Correo de Creación de Orden (MercadoPago Pendiente)
    try:
        user_email = current_user.email
        body = f"Hola {current_user.name},\n\nHemos registrado tu intención de pedido #{order.id}. Por favor, completa tu pago en Mercado Pago para que podamos comenzar a prepararlo.\n\n— Equipo Duncan Dhu 🍔"
        TicketService.send_email(user_email, f"Tu Pedido #{order.id} está pendiente de pago — Duncan Dhu", body)
    except Exception as e:
        logger.error("Error enviando email confirmacion MP: %s", e)

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

                # Correo de Confirmación de Pago y Cambio de Estado (Webhook MP)
                try:
                    if order.user and order.user.email:
                        body_webhook = f"Hola {order.user.name},\n\n¡Hemos recibido tu pago de MercadoPago (Ref: {payment_id}) para el pedido #{order.id}!\n\nEl estado de tu pedido ha cambiado a: '{order.status.upper()}'. Comenzaremos a prepararlo de inmediato.\n\n— Equipo Duncan Dhu 🍔"
                        TicketService.send_email(order.user.email, f"¡Pago exitoso para el pedido #{order.id}! — Duncan Dhu", body_webhook)
                except Exception as e:
                    logger.error("Error enviando email webhook MP: %s", e)

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
# Mis Pedidos
# ---------------------------------------------------------------------------
@public_bp.route("/mis-pedidos")
@login_required
def mis_pedidos():
    orders = (
        Order.query
        .filter_by(user_id=current_user.id, archived=False)
        .order_by(Order.created_at.desc())
        .all()
    )
    return render_template("public/mis_pedidos.html", orders=orders)


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
        phone = request.form.get("telefono", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not name:
            flash("El nombre es obligatorio", "error")
            return render_template("public/perfil.html")

        # Validar teléfono
        if phone and (not phone.isdigit() or len(phone) != 10):
            flash("El teléfono debe tener exactamente 10 dígitos", "error")
            return render_template("public/perfil.html")

        # Validar contraseña (solo si se proporcionó)
        if new_password:
            if len(new_password) < 6:
                flash("La contraseña debe tener al menos 6 caracteres", "error")
                return render_template("public/perfil.html")
            if new_password != confirm_password:
                flash("Las contraseñas no coinciden", "error")
                return render_template("public/perfil.html")

        # Detectar qué cambió para la notificación
        changes = []
        old_phone = current_user.phone or ""
        new_phone = phone or ""
        if old_phone != new_phone:
            changes.append("teléfono")

        # Aplicar cambios
        current_user.name = name
        current_user.phone = phone or None

        if new_password:
            current_user.set_password(new_password)
            changes.append("contraseña")

        db.session.commit()

        # Enviar correo de notificación si hubo cambios sensibles
        if changes and current_user.email:
            _send_profile_change_notification(
                current_user.email, current_user.name, changes
            )

        flash("Perfil actualizado correctamente", "success")

    return render_template("public/perfil.html")


def _send_profile_change_notification(
    email: str, name: str, changes: list
) -> None:
    """Envía un correo informativo cuando se modifican datos sensibles."""
    campos = " y ".join(changes)
    body = (
        f"Hola {name},\n\n"
        f"Te informamos que, por tu seguridad, tu perfil en Duncan Dhu "
        f"ha sido actualizado.\n\n"
        f"Se ha modificado tu {campos} exitosamente.\n\n"
        f"Si tú no realizaste este cambio, contacta a soporte de inmediato.\n\n"
        f"— Equipo Duncan Dhu 🍔"
    )
    try:
        TicketService.send_email(email, "Actualización de perfil — Duncan Dhu", body)
        logger.info("Notificación de cambio de perfil enviada a %s", email)
    except Exception as exc:
        logger.warning("No se pudo enviar notificación de perfil a %s: %s", email, exc)

# ---------------------------------------------------------------------------
# API Chatbot FSM (BFF - Backend For Frontend)
# ---------------------------------------------------------------------------

@public_bp.route("/api/bot/products", methods=["GET"])
def api_bot_products():
    """Action Hook FSM legacy — redirige al nuevo quick_menu."""
    return api_bot_quick_menu()


@public_bp.route("/api/bot/quick_menu", methods=["GET"])
def api_bot_quick_menu():
    """
    Action Hook FSM: Menú Rápido categorizado.
    Devuelve Hamburguesas (3), Snacks (2), Bebidas (2) con sus IDs reales de BD.
    """
    def _get_products_by_slug(slug, limit):
        from app.models import Category  # noqa
        cat = Category.query.filter_by(slug=slug).first()
        if not cat:
            return []
        return Product.query.filter_by(active=True, category_id=cat.id).limit(limit).all()

    burgers  = _get_products_by_slug("hamburguesas", 3)
    snacks   = _get_products_by_slug("snacks", 2)
    bebidas  = _get_products_by_slug("bebidas", 2)

    options = []

    # ── Hamburguesas ──────────────────────────────────────────────
    for p in burgers:
        options.append({
            "text": f"🍔 {p.name} — ${p.price}",
            "style": "primary",
            "mutationHookUrl": f"/carrito/agregar/{p.id}",
            "actionPayload": {"redirect_to": "ajax"},
            "next": "post_add_menu"
        })

    # ── Snacks ────────────────────────────────────────────────────
    for p in snacks:
        options.append({
            "text": f"🍟 {p.name} — ${p.price}",
            "style": "secondary",
            "mutationHookUrl": f"/carrito/agregar/{p.id}",
            "actionPayload": {"redirect_to": "ajax"},
            "next": "post_add_menu"
        })

    # ── Bebidas ───────────────────────────────────────────────────
    for p in bebidas:
        options.append({
            "text": f"🥤 {p.name} — ${p.price}",
            "style": "secondary",
            "mutationHookUrl": f"/carrito/agregar/{p.id}",
            "actionPayload": {"redirect_to": "ajax"},
            "next": "post_add_menu"
        })

    # ── Navegación ───────────────────────────────────────────────
    options.append({
        "text": "📖 Ver Menú Completo",
        "action": "() => window.location.href = '/catalogo'",
        "isLink": True,
        "style": "outline"
    })
    options.append({"text": "🔙 Regresar", "next": "start", "style": "outline"})

    return jsonify({
        "message": "Estas solo son algunas de nuestras opciones, haz click en lo que mas se te antoje y se agregará al carrito 👇",
        "options": options
    })


@public_bp.route("/api/bot/products_post_add", methods=["GET"])
def api_bot_products_post_add():
    """
    Action Hook FSM: Post-add menu categorizado.
    Igual que quick_menu pero con 'Proceder al Pago' en lugar de 'Regresar'.
    """
    def _get_products_by_slug(slug, limit):
        cat = Category.query.filter_by(slug=slug).first()
        if not cat:
            return []
        return Product.query.filter_by(active=True, category_id=cat.id).limit(limit).all()

    burgers = _get_products_by_slug("hamburguesas", 3)
    snacks  = _get_products_by_slug("snacks", 2)
    bebidas = _get_products_by_slug("bebidas", 2)

    options = []

    for p in burgers:
        options.append({
            "text": f"🍔 {p.name} — ${p.price}",
            "style": "primary",
            "mutationHookUrl": f"/carrito/agregar/{p.id}",
            "actionPayload": {"redirect_to": "ajax"},
            "next": "post_add_menu"
        })
    for p in snacks:
        options.append({
            "text": f"🍟 {p.name} — ${p.price}",
            "style": "secondary",
            "mutationHookUrl": f"/carrito/agregar/{p.id}",
            "actionPayload": {"redirect_to": "ajax"},
            "next": "post_add_menu"
        })
    for p in bebidas:
        options.append({
            "text": f"🥤 {p.name} — ${p.price}",
            "style": "secondary",
            "mutationHookUrl": f"/carrito/agregar/{p.id}",
            "actionPayload": {"redirect_to": "ajax"},
            "next": "post_add_menu"
        })

    options.append({
        "text": "📖 Ver Menú Completo",
        "action": "() => window.location.href = '/catalogo'",
        "isLink": True,
        "style": "outline"
    })
    # CTA al pago en lugar de "Regresar"
    options.append({
        "text": "💳 Proceder al Pago",
        "action": "() => window.location.href = '/carrito'",
        "isLink": True,
        "style": "primary"
    })

    return jsonify({
        "message": "¿Deseas agregar algo más? 🛒",
        "options": options
    })


@public_bp.route("/api/bot/order_status", methods=["GET"])
def api_bot_order_status():
    """
    Action Hook FSM: Consulta la última orden activa del current_user.
    NO usa @login_required para evitar un redirect HTML que rompe AJAX.
    En su lugar, hace una respuesta JSON amigable si no hay sesión.
    """
    if not current_user.is_authenticated:
        return jsonify({
            "message": "Necesitas iniciar sesión para ver el estado de tus pedidos. 🔒",
            "options": [
                { "text": "🔑 Iniciar Sesión", "action": "() => window.location.href = '/login'", "isLink": True, "style": "primary" },
                { "text": "Regresar", "next": "start", "style": "outline" }
            ]
        }), 200
    # Buscar última orden activa
    order = Order.query.filter(
        Order.user_id == current_user.id,
        Order.archived == False,
        Order.status != "completado",
        Order.status != "cancelado"
    ).order_by(Order.created_at.desc()).first()

    if not order:
        return jsonify({
            "message": "Actualmente no tienes ningún pedido en curso con nosotros.",
            "options": [
                { "text": "Ver Menú Rápido", "next": "bot_menu_hook", "style": "primary" },
                { "text": "Volver al inicio", "next": "start", "style": "outline" }
            ]
        })

    # Mapeo visual de estados
    status_msg = {
        "pendiente": "Tu orden está **Pendiente de confirmación**. ⏳",
        "preparando": "¡Estamos **Preparando** tus hamburguesas! 🔥",
        "listo": "¡Tu pedido está **Listo** para recoger/enviar! 🚀"
    }.get(order.status, f"Estado actual: **{order.status}**")

    message = f"Encontré tu último pedido (Ticket `#{order.id}`).\nTotal: **${order.total}**\n\n{status_msg}"

    return jsonify({
        "message": message,
        "options": [
            { "text": "Refrescar Estado 🔄", "next": "order_status_hook", "style": "primary" },
            { "text": "Ticket Confirmación 🧾", "action": f"() => window.location.href = '/ticket/{order.id}'", "isLink": True, "style": "secondary" },
            { "text": "Volver", "next": "start", "style": "outline" }
        ]
    })

