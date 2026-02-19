from datetime import datetime, timedelta
from decimal import Decimal
import io

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.extensions import db
from app.models import Product, Category, InventoryItem, Order


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for("auth.admin_login"))
        return func(*args, **kwargs)

    return wrapper


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    today = datetime.utcnow().date()
    orders_today = Order.query.filter(Order.created_at >= today).count()
    revenue_today = (
        db.session.query(db.func.coalesce(db.func.sum(Order.total), 0))
        .filter(Order.created_at >= today)
        .scalar()
    )
    product_count = Product.query.count()
    low_stock = InventoryItem.query.filter(InventoryItem.stock_current <= InventoryItem.stock_min).count()
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
        stock = request.form.get("stock")
        description = request.form.get("description", "")
        product = Product(
            name=name,
            category_id=category_id or None,
            price=Decimal(price or 0),
            description=description,
            active=True,
        )
        db.session.add(product)
        db.session.commit()
        flash("Producto agregado", "success")
        return redirect(url_for("admin.products"))

    products = Product.query.all()
    return render_template(
        "admin-productos.html",
        products=products,
        categories=categories,
    )


@admin_bp.route("/productos/<int:product_id>/estado", methods=["POST"])
@login_required
@admin_required
def product_toggle(product_id: int):
    product = Product.query.get_or_404(product_id)
    try:
        db.session.delete(product)
        db.session.commit()
        flash("Producto eliminado", "success")
    except IntegrityError:
        db.session.rollback()
        product.active = False
        db.session.commit()
        flash("No se pudo eliminar por historial. Se desactivo el producto.", "error")
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
        flash("Insumo agregado", "success")
        return redirect(url_for("admin.inventory"))

    items = InventoryItem.query.all()
    return render_template("admin-inventario.html", items=items)


@admin_bp.route("/inventario/<int:item_id>/estado", methods=["POST"])
@login_required
@admin_required
def inventory_toggle(item_id: int):
    item = InventoryItem.query.get_or_404(item_id)
    item.active = not item.active
    db.session.commit()
    return redirect(url_for("admin.inventory"))


@admin_bp.route("/ordenes")
@login_required
@admin_required
def orders():
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
    start, _ = _report_range(range_type)

    orders = Order.query.filter(Order.created_at >= start).all()
    total_revenue = sum((o.total for o in orders), Decimal("0"))
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
            pdf.drawString(40, y, f"#{order.id}")
            pdf.drawString(90, y, order.created_at.strftime("%d/%m/%Y %H:%M"))
            pdf.drawString(200, y, (order.user.name if order.user else "Invitado")[:18])
            pdf.drawString(330, y, f"${order.total:.2f}")
            pdf.drawString(400, y, order.status)
            pdf.drawString(470, y, order.payment_method)
            y -= 14

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"reporte_{range_type}.pdf"
    return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=filename)
