import logging
import smtplib
from email.mime.text import MIMEText
from typing import Dict, List

import mercadopago
from flask import current_app
from twilio.rest import Client

from app.extensions import db
from app.models import Order, ProductRecipe


logger = logging.getLogger(__name__)


class PaymentService:
    @staticmethod
    def create_preference(order_id: int, items: List[Dict]) -> Dict:
        access_token = current_app.config.get("MP_ACCESS_TOKEN")
        if not access_token:
            raise RuntimeError("MP_ACCESS_TOKEN no configurado")

        sdk = mercadopago.SDK(access_token)
        base_url = current_app.config.get("BASE_URL")
        preference_data = {
            "items": items,
            "external_reference": str(order_id),
            "back_urls": {
                "success": f"{base_url}/mp/return?status=success",
                "pending": f"{base_url}/mp/return?status=pending",
                "failure": f"{base_url}/mp/return?status=failure",
            },
            "auto_return": "approved",
            "notification_url": f"{base_url}/mp/webhook",
        }
        preference_response = sdk.preference().create(preference_data)
        return preference_response["response"]


class InventoryService:
    """Servicio atómico e idempotente para descuento de stock."""

    @staticmethod
    def deduct_stock(order: Order) -> bool:
        """Descuenta insumos del inventario según las recetas de cada OrderItem.

        Es idempotente: si ``order.stock_processed`` ya es True, no hace nada.
        Retorna True si el descuento se realizó, False si ya estaba procesado.

        Raises:
            ValueError: si el stock resultante sería negativo para algún insumo.
        """
        if order.stock_processed:
            logger.info(
                "Stock ya descontado para la orden #%s, omitiendo.", order.id
            )
            return False

        try:
            for order_item in order.items:
                recipes: List[ProductRecipe] = ProductRecipe.query.filter_by(
                    product_id=order_item.product_id
                ).all()

                for recipe in recipes:
                    inv_item = recipe.inventory_item
                    amount_to_deduct = recipe.quantity_required * order_item.quantity
                    new_stock = inv_item.stock_current - amount_to_deduct

                    if new_stock < 0:
                        raise ValueError(
                            f"Stock insuficiente para '{inv_item.name}': "
                            f"disponible={inv_item.stock_current}, "
                            f"requerido={amount_to_deduct}"
                        )

                    inv_item.stock_current = int(new_stock)

            order.stock_processed = True
            db.session.commit()
            logger.info("Stock descontado correctamente para la orden #%s.", order.id)
            return True

        except ValueError:
            db.session.rollback()
            logger.warning(
                "Descuento de stock fallido para la orden #%s — stock insuficiente.",
                order.id,
            )
            raise
        except Exception:
            db.session.rollback()
            logger.exception(
                "Error inesperado al descontar stock de la orden #%s.", order.id
            )
            raise


class TicketService:
    @staticmethod
    def build_ticket_message(order: Order, customer_name: str = "") -> str:
        """Construye el texto del ticket de una orden."""
        lines = [
            f"🎫 Ticket Duncan Dhu — Orden #{order.id}",
            f"Cliente: {customer_name or 'N/A'}",
            f"Método de pago: {order.payment_method}",
            "─" * 30,
        ]
        for item in order.items:
            lines.append(f"  {item.quantity}x {item.name}  ${item.price:.2f}")
        lines.append("─" * 30)
        lines.append(f"Total: ${order.total:.2f}")
        return "\n".join(lines)

    @staticmethod
    def send_email(to_email: str, subject: str, body: str) -> None:
        host = current_app.config.get("SMTP_HOST")
        port = current_app.config.get("SMTP_PORT")
        user = current_app.config.get("SMTP_USER")
        password = current_app.config.get("SMTP_PASSWORD")
        sender = current_app.config.get("SMTP_FROM")

        if not host or not user or not password:
            raise RuntimeError("SMTP no configurado")

        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = to_email

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(sender, [to_email], message.as_string())

    @staticmethod
    def send_whatsapp(to_number: str, body: str) -> None:
        account_sid = current_app.config.get("TWILIO_ACCOUNT_SID")
        auth_token = current_app.config.get("TWILIO_AUTH_TOKEN")
        from_number = current_app.config.get("TWILIO_WHATSAPP_FROM")

        if not account_sid or not auth_token or not from_number:
            raise RuntimeError("Twilio WhatsApp no configurado")

        client = Client(account_sid, auth_token)
        client.messages.create(
            from_=from_number,
            to=f"whatsapp:{to_number}",
            body=body,
        )
