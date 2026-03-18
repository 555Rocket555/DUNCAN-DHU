"""
Servicios de mensajería: Email (Brevo REST API) y WhatsApp (Twilio).

EmailService: Envío de correos vía API REST de Brevo (HTTPS).
  – No usa SMTP ni puertos 25/587 (bloqueados en Render Free Tier).
  – Requiere la variable de entorno BREVO_API_KEY.

TicketService: Construcción y envío de tickets de orden.
"""

import logging
import os
import traceback

import requests
from flask import current_app
from twilio.rest import Client

from app.models import Order

logger = logging.getLogger(__name__)

# ── Brevo REST API ────────────────────────────────────────────────────────────
_BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


# ── EmailService ──────────────────────────────────────────────────────────────

class EmailService:
    """
    Envía correos vía API REST de Brevo (no SMTP).
    Render Free Tier bloquea el puerto 587; la API REST usa HTTPS (443).
    Requiere la variable de entorno BREVO_API_KEY.
    """

    @staticmethod
    def is_configured() -> bool:
        """True si BREVO_API_KEY está definida en el entorno."""
        return bool(os.getenv("BREVO_API_KEY"))

    @staticmethod
    def send(to_email: str, subject: str, body_text: str, body_html: str = "") -> bool:
        """
        Envía un correo usando la API REST de Brevo.

        Args:
            to_email:  Dirección del destinatario.
            subject:   Asunto del correo.
            body_text: Texto plano (fallback de accesibilidad).
            body_html: HTML completo del correo (preferido por Brevo).

        Returns:
            True si la API respondió 2xx, False en cualquier otro caso.
        """
        api_key = os.getenv("BREVO_API_KEY", "")
        sender_email = current_app.config.get("SMTP_FROM", "no-reply@duncandhu.com")

        print(
            f"📧 [EmailService] Enviando a: {to_email} | "
            f"sender={sender_email} | api_key={'***' if api_key else 'VACÍA'}",
            flush=True,
        )

        if not api_key:
            print(
                "⚠️ [EmailService] BREVO_API_KEY no configurada — correo descartado.",
                flush=True,
            )
            logger.warning("BREVO_API_KEY ausente — correo a %s descartado", to_email)
            return False

        payload = {
            "sender":      {"name": "Duncan Dhu", "email": sender_email},
            "to":          [{"email": to_email}],
            "subject":     subject,
            "htmlContent": body_html or f"<pre>{body_text}</pre>",
        }

        # body_text como alternativa de texto plano (opcional pero recomendado)
        if body_text:
            payload["textContent"] = body_text

        headers = {
            "api-key":      api_key,
            "Content-Type": "application/json",
            "Accept":       "application/json",
        }

        try:
            response = requests.post(
                _BREVO_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=15,   # 15s — la API de Brevo es rápida
            )

            if response.status_code in (200, 201, 202):
                msg_id = response.json().get("messageId", "?")
                print(
                    f"✅ [EmailService] Correo enviado. messageId={msg_id}",
                    flush=True,
                )
                logger.info("Correo enviado a %s — messageId=%s", to_email, msg_id)
                return True

            # Respuesta no-2xx → error de la API
            print(
                f"🚨 [EmailService] Brevo API error {response.status_code}: "
                f"{response.text}",
                flush=True,
            )
            logger.error(
                "Brevo API %s para correo a %s: %s",
                response.status_code, to_email, response.text,
            )
            return False

        except requests.exceptions.Timeout:
            print("🚨 [EmailService] Timeout al conectar con Brevo API.", flush=True)
            logger.error("Timeout enviando correo a %s", to_email)
        except requests.exceptions.RequestException as exc:
            print(f"🚨 [EmailService] RequestException: {exc}", flush=True)
            traceback.print_exc()
            logger.error("RequestException enviando correo a %s: %s", to_email, exc)
        except Exception as exc:  # noqa: BLE001
            print(f"🚨 ERROR CRÍTICO DE CORREO: {exc}", flush=True)
            traceback.print_exc()
            logger.error("Error crítico enviando correo a %s: %s", to_email, exc)

        return False



# ── TicketService ─────────────────────────────────────────────────────────────

class TicketService:
    """Construcción y despacho de tickets de órdenes."""

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
    def send_email(to_email: str, subject: str, body: str) -> bool:
        """Envía un correo de ticket (delega a EmailService)."""
        return EmailService.send(to_email, subject, body)

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
