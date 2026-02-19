from datetime import datetime, timedelta
from decimal import Decimal
import io

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.extensions import db
from app.models import Product, Category, InventoryItem, Order, User


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
    today = datetime.utcnow().date()
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
        # Note: 'active' defaults to True for new products
        
        try:
            product = Product(
                name=name,
                category_id=category_id if category_id else None,
                price=Decimal(price or 0),
                description=description,
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


def _report_range(range_type: str) -> tuple[datetime, str]:
    now = datetime.utcnow()
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
    # Auto-eliminar ordenes antiguas (mas de 3 minutos de antiguedad si estan completadas o canceladas)
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=3)
        # Solo eliminamos las completadas o canceladas para no borrar pedidos recientes pendientes
        deleted_count = Order.query.filter(
            Order.status.in_(['completado', 'cancelado']),
            Order.created_at < cutoff
        ).delete(synchronize_session=False)
        
        if deleted_count > 0:
            db.session.commit()
            # Opcional: flash(f"Se limpiaron {deleted_count} ordenes antiguas.", "info")
    except Exception as e:
        db.session.rollback()
        # print(f"Error limpiando ordenes: {e}")

    orders = Order.query.order_by(Order.created_at.desc()).all()
    stats = {
        "total": len(orders),
        "pendientes": len([o for o in orders if o.status == "pendiente"]),
        "preparando": len([o for o in orders if o.status == "preparando"]),
        "listos": len([o for o in orders if o.status == "listo"]),
        "completados": len([o for o in orders if o.status == "completado"]),
    }
    return render_template("admin-órdenes.html", orders=orders, stats=stats)


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
    pdf.drawString(40, y, f"Generado: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC")
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
