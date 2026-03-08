from flask import Blueprint, jsonify, request
from flask_login import login_required

from app.models import Product, Category, InventoryItem, Order
from app.services import chat_service


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
                "available": p.is_available(),
            }
            for p in products
        ]
    )


@api_bp.get("/orders/<int:order_id>")
@login_required
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


@api_bp.post("/chat")
@login_required
def api_chat():
    """Endpoint para el chatbot. Recibe un JSON ``{"message": "..."}``."""
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "")

    if not user_message.strip():
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400

    result = chat_service.process_message(user_message)
    return jsonify(result)
