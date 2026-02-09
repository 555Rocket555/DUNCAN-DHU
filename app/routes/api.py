from flask import Blueprint, jsonify

from app.models import Product, Order


api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.get("/products")
def api_products():
    products = Product.query.filter_by(active=True).all()
    return jsonify(
        [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": float(p.price),
                "image_url": p.image_url,
                "category": p.category.name if p.category else None,
            }
            for p in products
        ]
    )


@api_bp.get("/orders/<int:order_id>")
def api_order(order_id: int):
    order = Order.query.get_or_404(order_id)
    return jsonify(
        {
            "id": order.id,
            "status": order.status,
            "payment_status": order.payment_status,
            "payment_method": order.payment_method,
            "total": float(order.total),
            "items": [
                {
                    "product_id": item.product_id,
                    "name": item.name,
                    "price": float(item.price),
                    "quantity": item.quantity,
                }
                for item in order.items
            ],
        }
    )
