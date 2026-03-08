"""Servicio de chat — stub para futuro chatbot de Duncan Dhu."""

from __future__ import annotations

from app.models import Product, Category, InventoryItem


def process_message(user_message: str) -> dict:
    """Procesa un mensaje del usuario y retorna una respuesta.

    Por ahora devuelve un mensaje de mantenimiento.
    En producción, este servicio consultará ``Product``, ``Category`` e
    ``InventoryItem`` para responder sobre disponibilidad, precios, etc.
    """
    _ = user_message  # será utilizado cuando el chatbot esté activo

    return {
        "reply": (
            "🔧 Servicio en mantenimiento. "
            "Nuestro asistente virtual estará disponible pronto."
        ),
        "status": "maintenance",
    }
