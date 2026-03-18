from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.extensions import db
from app.models import Product, Category, InventoryItem, ProductRecipe, Order, User
import cloudinary.uploader


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Acceso denegado. Se requieren permisos de administrador.", "error")
            return redirect(url_for("public.home"))
        return func(*args, **kwargs)

    return wrapper


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    today = datetime.now(timezone.utc).date()
    orders_today = Order.query.filter(db.func.date(Order.created_at) == today).count()
    revenue_today = (
        db.session.query(db.func.coalesce(db.func.sum(Order.total), 0))
        .filter(db.func.date(Order.created_at) == today)
        .scalar()
    )
    product_count = Product.query.count()
    low_stock = InventoryItem.query.filter(
        InventoryItem.stock_current <= InventoryItem.stock_min
    ).count()
    return render_template(
        "dashboard-admin.html",
        orders_today=orders_today,
        revenue_today=revenue_today,
        product_count=product_count,
        low_stock=low_stock,
    )


@admin_bp.route("/productos", methods=["GET", "POST"])
@login_required
@admin_required
def products():
    categories = Category.query.all()
    if request.method == "POST":
        name = request.form.get("name")
        category_id = request.form.get("category_id")
        price = request.form.get("price")
        description = request.form.get("description", "")

        # Detección y subida de imagen a Cloudinary
        file = request.files.get("image_file")
        image_url = ""
        if file and file.filename:
            print(f"📸 Archivo detectado: {file.filename}")
            try:
                upload_result = cloudinary.uploader.upload(file)
                image_url = upload_result.get("secure_url", "")
                print(f"✅ Imagen subida: {image_url}")
            except Exception as e:
                print(f"❌ Error al subir imagen: {e}")
                flash(f"Error al subir imagen: {str(e)}", "error")
        
        try:
            product = Product(
                name=name,
                category_id=category_id if category_id else None,
                price=Decimal(price or 0),
                description=description,
                image_url=image_url,
                active=True,
            )
            db.session.add(product)
            db.session.commit()
            flash("Producto agregado correctamente", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al agregar producto: {str(e)}", "error")
            
        return redirect(url_for("admin.products"))

    products = Product.query.all()
    return render_template(
        "admin-productos.html",
        products=products,
        categories=categories,
    )


@admin_bp.route("/productos/<int:product_id>/editar", methods=["POST"])
@login_required
@admin_required
def product_edit(product_id: int):
    product = Product.query.get_or_404(product_id)
    try:
        product.name = request.form.get("name")
        category_id = request.form.get("category_id")
        product.category_id = category_id if category_id else None
        product.price = Decimal(request.form.get("price") or 0)
        product.description = request.form.get("description", "")

        # Detección y subida de imagen a Cloudinary
        file = request.files.get("image_file")
        if file and file.filename:
            print(f"📸 Archivo detectado (edición): {file.filename}")
            try:
                upload_result = cloudinary.uploader.upload(file)
                product.image_url = upload_result.get("secure_url", "")
                print(f"✅ Imagen actualizada: {product.image_url}")
            except Exception as e:
                print(f"❌ Error al subir imagen: {e}")
                flash(f"Error al subir imagen: {str(e)}", "error")
        
        db.session.commit()
        flash("Producto actualizado correctamente", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al actualizar: {str(e)}", "error")
        
    return redirect(url_for("admin.products"))


@admin_bp.route("/productos/<int:product_id>/eliminar", methods=["POST"])
@login_required
@admin_required
def product_delete(product_id: int):
    product = Product.query.get_or_404(product_id)
    try:
        db.session.delete(product)
        db.session.commit()
        flash("Producto eliminado permanentemente", "success")
    except IntegrityError:
        db.session.rollback()
        product.active = False
        db.session.commit()
        flash("No se pudo eliminar por historial de ordenes. Se ha desactivado.", "warning")
    return redirect(url_for("admin.products"))


@admin_bp.route("/productos/<int:product_id>/estado", methods=["POST"])
@login_required
@admin_required
def product_toggle(product_id: int):
    product = Product.query.get_or_404(product_id)
    product.active = not product.active
    db.session.commit()
    flash(f"Producto {'activado' if product.active else 'desactivado'}", "success")
    return redirect(url_for("admin.products"))


# ---------------------------------------------------------------------------
# Recetas de producto
# ---------------------------------------------------------------------------
@admin_bp.route("/productos/<int:product_id>/receta", methods=["GET", "POST"])
@login_required
@admin_required
def product_recipe(product_id: int):
    product = Product.query.get_or_404(product_id)
    if request.method == "POST":
        inventory_item_id = request.form.get("inventory_item_id")
        quantity = request.form.get("quantity_required")
        try:
            recipe = ProductRecipe(
                product_id=product.id,
                inventory_item_id=int(inventory_item_id),
                quantity_required=float(quantity or 1),
            )
            db.session.add(recipe)
            db.session.commit()
            flash("Ingrediente agregado a la receta", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al agregar ingrediente: {str(e)}", "error")
        return redirect(url_for("admin.product_recipe", product_id=product.id))

    recipes = ProductRecipe.query.filter_by(product_id=product.id).all()
    inventory_items = InventoryItem.query.filter_by(active=True).all()
    return render_template(
        "admin-receta.html",
        product=product,
        recipes=recipes,
        inventory_items=inventory_items,
    )


@admin_bp.route("/productos/<int:product_id>/receta/<int:recipe_id>/editar", methods=["POST"])
@login_required
@admin_required
def recipe_edit(product_id: int, recipe_id: int):
    recipe = ProductRecipe.query.get_or_404(recipe_id)
    try:
        recipe.quantity_required = float(request.form.get("quantity_required") or 1)
        db.session.commit()
        flash("Cantidad actualizada", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {str(e)}", "error")
    return redirect(url_for("admin.product_recipe", product_id=product_id))


@admin_bp.route("/productos/<int:product_id>/receta/<int:recipe_id>/eliminar", methods=["POST"])
@login_required
@admin_required
def recipe_delete(product_id: int, recipe_id: int):
    recipe = ProductRecipe.query.get_or_404(recipe_id)
    db.session.delete(recipe)
    db.session.commit()
    flash("Ingrediente eliminado de la receta", "success")
    return redirect(url_for("admin.product_recipe", product_id=product_id))


def _report_range(range_type: str) -> tuple[datetime, str]:
    now = datetime.now(timezone.utc)
    if range_type == "week":
        return now - timedelta(days=7), "Reporte semanal"
    if range_type == "month":
        return now - timedelta(days=30), "Reporte mensual"
    return now.replace(hour=0, minute=0, second=0, microsecond=0), "Reporte del dia"


@admin_bp.route("/inventario", methods=["GET", "POST"])
@login_required
@admin_required
def inventory():
    if request.method == "POST":
        try:
            item = InventoryItem(
                name=request.form.get("name"),
                stock_min=int(request.form.get("stock_min") or 0),
                stock_current=int(request.form.get("stock_current") or 0),
                price=Decimal(request.form.get("price") or 0),
                provider=request.form.get("provider", ""),
                active=True,
            )
            db.session.add(item)
            db.session.commit()
            flash("Insumo agregado correctamente", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al agregar insumo: {str(e)}", "error")
            
        return redirect(url_for("admin.inventory"))

    items = InventoryItem.query.all()
    return render_template("admin-inventario.html", items=items)


@admin_bp.route("/inventario/<int:item_id>/editar", methods=["POST"])
@login_required
@admin_required
def inventory_edit(item_id: int):
    item = InventoryItem.query.get_or_404(item_id)
    try:
        item.name = request.form.get("name")
        item.stock_min = int(request.form.get("stock_min") or 0)
        item.stock_current = int(request.form.get("stock_current") or 0)
        item.price = Decimal(request.form.get("price") or 0)
        item.provider = request.form.get("provider", "")
        
        db.session.commit()
        flash("Insumo actualizado correctamente", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error al actualizar insumo: {str(e)}", "error")
        
    return redirect(url_for("admin.inventory"))


@admin_bp.route("/inventario/<int:item_id>/eliminar", methods=["POST"])
@login_required
@admin_required
def inventory_delete(item_id: int):
    item = InventoryItem.query.get_or_404(item_id)
    try:
        db.session.delete(item)
        db.session.commit()
        flash("Insumo eliminado permanentemente", "success")
    except IntegrityError:
        db.session.rollback()
        item.active = False
        db.session.commit()
        flash("No se puede eliminar por uso en sistema. Se ha desactivado.", "warning")
    return redirect(url_for("admin.inventory"))


@admin_bp.route("/inventario/<int:item_id>/estado", methods=["POST"])
@login_required
@admin_required
def inventory_toggle(item_id: int):
    item = InventoryItem.query.get_or_404(item_id)
    item.active = not item.active
    db.session.commit()
    flash(f"Insumo {'activado' if item.active else 'desactivado'}", "success")
    return redirect(url_for("admin.inventory"))


@admin_bp.route("/ordenes")
@login_required
@admin_required
def orders():
    # Leer filtro de estado opcional
    active_filter = request.args.get("estado", "").strip().lower() or None

    # Always get ALL orders for computing stats (unarchived)
    all_orders = Order.query.filter_by(archived=False).all()
    stats = {
        "total":      len(all_orders),
        "pendientes": len([o for o in all_orders if o.status == "pendiente"]),
        "preparando": len([o for o in all_orders if o.status == "preparando"]),
        "listos":     len([o for o in all_orders if o.status == "listo"]),
        "completados":len([o for o in all_orders if o.status == "completado"]),
        "cancelados": len([o for o in all_orders if o.status == "cancelado"]),
    }

    # Filtrar para la tabla si hay filtro activo
    q = Order.query.filter_by(archived=False)
    if active_filter:
        q = q.filter_by(status=active_filter)
    orders = q.order_by(Order.created_at.desc()).all()

    return render_template("admin-ordenes.html", orders=orders, stats=stats, active_filter=active_filter)


@admin_bp.route("/ordenes/<int:order_id>/eliminar", methods=["POST"])
@login_required
@admin_required
def order_delete(order_id: int):
    order = Order.query.get_or_404(order_id)
    order.archived = True
    db.session.commit()
    flash("Orden archivada correctamente", "success")
    return redirect(url_for("admin.orders"))


@admin_bp.route("/ordenes/<int:order_id>/status", methods=["POST"])
@login_required
@admin_required
def order_update_status(order_id: int):
    """Cambia el estado de una orden (desde el select inline o botones de acción)."""
    valid_statuses = {"pendiente", "preparando", "listo", "completado", "cancelado"}
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get("status", "").strip().lower()
    if new_status not in valid_statuses:
        flash(f"Estado '{new_status}' inválido", "error")
        return redirect(url_for("admin.orders"))
    old_status = order.status
    order.status = new_status
    db.session.commit()
    flash(f"Orden #{order_id}: {old_status} → {new_status}", "success")
    # Regresar al mismo filtro que estaba activo
    active_filter = request.args.get("estado") or new_status
    return redirect(url_for("admin.orders"))


@admin_bp.route("/reportes")
@login_required
@admin_required
def reports():
    range_type = request.args.get("range", "day")
    custom_date = request.args.get("custom_date")

    if range_type == "custom" and custom_date:
        try:
            start_date = datetime.strptime(custom_date, "%Y-%m-%d")
            start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            # Override _report_range result
        except ValueError:
            flash("Fecha inválida", "error")
            start, _ = _report_range("day")
            end = None # _report_range logic usually implies "from X until now"
    else:
        start, _ = _report_range(range_type)
        end = None

    if end:
         orders = Order.query.filter(Order.created_at >= start, Order.created_at < end).all()
    else:
         orders = Order.query.filter(Order.created_at >= start).all()

    total_revenue = sum((o.total for o in orders if o.status in ["completado", "preparando", "listo"]), Decimal("0"))
    completed = len([o for o in orders if o.status == "completado"])
    pending = len([o for o in orders if o.status == "pendiente"])
    cancelled = len([o for o in orders if o.status == "cancelado"])
    avg_ticket = total_revenue / completed if completed else Decimal("0")

    return render_template(
        "admin-reportes.html",
        total_revenue=total_revenue,
        completed=completed,
        avg_ticket=avg_ticket,
        pending=pending,
        cancelled=cancelled,
        orders=orders,
        range_type=range_type,
    )


@admin_bp.route("/reportes/pdf")
@login_required
@admin_required
def reports_pdf():
    range_type = request.args.get("range", "day")
    start, title = _report_range(range_type)
    orders = Order.query.filter(Order.created_at >= start).order_by(Order.created_at.desc()).all()

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, f"{title} - Duncan Dhu")
    y -= 24
    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, y, f"Generado: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC")
    y -= 20

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "ID")
    pdf.drawString(90, y, "Fecha")
    pdf.drawString(200, y, "Cliente")
    pdf.drawString(330, y, "Total")
    pdf.drawString(400, y, "Estado")
    pdf.drawString(470, y, "Pago")
    y -= 16
    pdf.setFont("Helvetica", 9)

    if not orders:
        pdf.drawString(40, y, "Sin registros para este rango.")
    else:
        for order in orders:
            if y < 60:
                pdf.showPage()
                y = height - 50
                pdf.setFont("Helvetica-Bold", 10)
                pdf.drawString(40, y, "ID")
                pdf.drawString(90, y, "Fecha")
                pdf.drawString(200, y, "Cliente")
                pdf.drawString(330, y, "Total")
                pdf.drawString(400, y, "Estado")
                pdf.drawString(470, y, "Pago")
                y -= 16
                pdf.setFont("Helvetica", 9)
            
            p_method = getattr(order, 'payment_method', 'N/A') # Safety check if model doesn't have it
            pdf.drawString(40, y, f"#{order.id}")
            pdf.drawString(90, y, order.created_at.strftime("%d/%m/%Y %H:%M"))
            pdf.drawString(200, y, (order.user.name if order.user else "Invitado")[:18])
            pdf.drawString(330, y, f"${order.total:.2f}")
            pdf.drawString(400, y, order.status)
            pdf.drawString(470, y, str(p_method))
            y -= 14

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"reporte_{range_type}.pdf"
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)


@admin_bp.route("/usuarios")
@login_required
@admin_required
def users_list():
    users = User.query.all()
    return render_template("admin-usuarios.html", users=users)


@admin_bp.route("/usuarios/<int:user_id>/eliminar", methods=["POST"])
@login_required
@admin_required
def user_delete(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("No puedes eliminar tu propia cuenta de administrador", "error")
        return redirect(url_for("admin.users_list"))
        
    try:
        db.session.delete(user)
        db.session.commit()
        flash("Usuario eliminado correctamente", "success")
    except Exception as e:
        db.session.rollback()
        flash("Error al eliminar usuario (posiblemente tenga ordenes asociadas).", "error")
            
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/usuarios/crear", methods=["POST"])
@login_required
@admin_required
def user_create():
    name = request.form.get("nombre", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("telefono", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("contrasena", "")
    is_admin = request.form.get("is_admin") == "1"

    if not name or not email or not password:
        flash("Nombre, correo y contraseña son obligatorios", "error")
        return redirect(url_for("admin.users_list"))

    if User.query.filter_by(email=email).first():
        flash("Ese correo ya está registrado", "error")
        return redirect(url_for("admin.users_list"))

    # Validar teléfono
    if phone and (not phone.isdigit() or len(phone) != 10):
        flash("El teléfono debe tener exactamente 10 dígitos", "error")
        return redirect(url_for("admin.users_list"))

    final_username = username or email
    if final_username != email and User.query.filter_by(username=final_username).first():
        flash("Ese nombre de usuario ya está en uso", "error")
        return redirect(url_for("admin.users_list"))

    user = User(
        name=name,
        email=email,
        phone=phone or None,
        username=final_username,
        is_admin=is_admin,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f"Usuario '{name}' creado exitosamente", "success")
    return redirect(url_for("admin.users_list"))


# ---------------------------------------------------------------------------
# API Chatbot FSM (BFF - Backend For Frontend) - Admin Command Center
# ---------------------------------------------------------------------------

@admin_bp.route("/api/bot/admin/orders_active", methods=["GET"])
@login_required
@admin_required
def api_bot_admin_orders_active():
    """
    Action Hook FSM: Retorna un resumen de las órdenes del día que están en proceso.
    """
    today = datetime.now(timezone.utc).date()
    orders = Order.query.filter(
        db.func.date(Order.created_at) == today,
        Order.archived == False,
        Order.status.in_(["pendiente", "preparando", "listo"])
    ).all()

    if not orders:
        return jsonify({
            "message": "Actualmente no hay pedidos activos en cola. ¡Buen trabajo! 🎉",
            "options": [
                { "text": "Regresar al Panel", "next": "start", "style": "primary" }
            ]
        })

    lines = []
    for o in orders:
        lines.append(f"• **#{o.id}** ({o.status.upper()}) - ${o.total}")

    message = f"📦 Hay **{len(orders)}** pedidos activos en este momento:\n\n" + "\n".join(lines)

    return jsonify({
        "message": message,
        "options": [
            { "text": "Mutar Estados", "next": "admin_mutate_orders_hook", "style": "primary" },
            { "text": "Ver en Dashboard", "action": "() => window.location.href = '/admin/ordenes'", "isLink": True, "style": "secondary" },
            { "text": "Regresar", "next": "start", "style": "outline" }
        ]
    })


@admin_bp.route("/api/bot/admin/orders_pending", methods=["GET"])
@login_required
@admin_required
def api_bot_admin_orders_pending():
    """
    Action Hook FSM: Renderiza botones por cada orden pendiente para permitir su mutación de estado directa.
    """
    today = datetime.now(timezone.utc).date()
    # Solo mostramos pedidos que pueden "avanzar" y no están terminados/listos del todo
    orders = Order.query.filter(
        db.func.date(Order.created_at) == today,
        Order.archived == False,
        Order.status.in_(["pendiente", "preparando"])
    ).all()

    if not orders:
        return jsonify({
            "message": "No hay pedidos pendientes de avance en este momento.",
            "options": [
                { "text": "Regresar", "next": "start", "style": "primary" }
            ]
        })

    options = []
    for o in orders:
        next_state = "preparando" if o.status == "pendiente" else "listo"
        options.append({
            "text": f"Mover #{o.id} a '{next_state.upper()}'",
            "style": "primary",
            "mutationHookUrl": f"/admin/api/bot/admin/order/{o.id}/next_state",
            "next": "admin_mutate_orders_hook"  # Recarga la lista para continuar mutando
        })

    options.append({ "text": "Regresar al Panel", "next": "start", "style": "outline" })

    return jsonify({
        "message": "¿Qué pedido deseas avanzar en la línea de cocina?",
        "options": options
    })


@admin_bp.route("/api/bot/admin/order/<int:order_id>/next_state", methods=["POST"])
@login_required
@admin_required
def api_bot_admin_order_next_state(order_id: int):
    """
    Action Hook Mutator: Transiciona al siguiente estado de la máquina en base de datos.
    """
    order = Order.query.get_or_404(order_id)
    
    old_status = order.status
    if order.status == "pendiente":
        order.status = "preparando"
    elif order.status == "preparando":
        order.status = "listo"
    elif order.status == "listo":
        order.status = "completado"
        
    db.session.commit()

    return jsonify({
        "message": f"✅ La orden **#{order.id}** pasó de '{old_status}' a '{order.status}'.",
        "options": [
            { "text": "Continuar operando", "next": "admin_mutate_orders_hook", "style": "primary" },
            { "text": "Regresar al Panel", "next": "start", "style": "outline" }
        ]
    })


@admin_bp.route("/api/bot/admin/sales_today", methods=["GET"])
@login_required
@admin_required
def api_bot_admin_sales_today():
    """
    Action Hook FSM: Calcula las ventas del día actual.
    """
    today = datetime.now(timezone.utc).date()
    revenue_today = (
        db.session.query(db.func.coalesce(db.func.sum(Order.total), 0))
        .filter(
            db.func.date(Order.created_at) == today,
            Order.status.in_(["completado", "preparando", "listo"]),
            Order.archived == False
        )
        .scalar()
    )
    
    orders_count = Order.query.filter(
        db.func.date(Order.created_at) == today,
        Order.status.in_(["completado", "preparando", "listo"]),
        Order.archived == False
    ).count()

    message = f"📈 **Métricas Financieras del Día:**\n\nIngresos brutos: **${revenue_today}**\nTickets procesados: **{orders_count}**"

    return jsonify({
        "message": message,
        "options": [
            { "text": "Ir a Reportes Detallados", "action": "() => window.location.href = '/admin/reportes'", "isLink": True, "style": "primary" },
            { "text": "Regresar al Panel", "next": "start", "style": "outline" }
        ]
    })

