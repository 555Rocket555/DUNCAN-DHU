"""
Servicios de mensajería: Email (SMTP) y WhatsApp (Twilio).

EmailService: Servicio SMTP zero-dependency usando la librería estándar de Python.
Aplica STARTTLS obligatorio y degradación graciosa ante fallos de red/auth.

TicketService: Construcción y envío de tickets de orden.
"""

import logging
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app
from twilio.rest import Client

from app.models import Order

logger = logging.getLogger(__name__)


# ── EmailService ──────────────────────────────────────────────────────────────

class EmailService:
    """
    Servicio SMTP zero-dependency.
    Responsabilidad única: construir y enviar correos vía SMTP relay.
    """

    @staticmethod
    def _get_config() -> dict:
        """Extrae la configuración SMTP del contexto de la app."""
        return {
            "host": current_app.config.get("SMTP_HOST", ""),
            "port": current_app.config.get("SMTP_PORT", 587),
            "user": current_app.config.get("SMTP_USER", ""),
            "password": current_app.config.get("SMTP_PASSWORD", ""),
            "sender": current_app.config.get("SMTP_FROM", "no-reply@duncandhu.local"),
        }

    @staticmethod
    def is_configured() -> bool:
        """Verifica si las variables SMTP mínimas están presentes."""
        cfg = EmailService._get_config()
        return bool(cfg["host"] and cfg["user"] and cfg["password"])

    @staticmethod
    def send(to_email: str, subject: str, body_text: str, body_html: str = "") -> bool:
        """
        Envía un correo vía SMTP con STARTTLS obligatorio.
        MODO DEBUG — envío síncrono garantizado. Apto para Gunicorn/Render.

        Args:
            to_email: Dirección del destinatario.
            subject: Asunto del correo.
            body_text: Contenido en texto plano (obligatorio para accesibilidad).
            body_html: Contenido HTML opcional (para clientes que lo soporten).

        Returns:
            True si se envió exitosamente, False si hubo fallo (degradación graciosa).
        """
        import traceback  # noqa: PLC0415 – debug import

        cfg = EmailService._get_config()

        print(
            f"📧 [EmailService] Intentando enviar a: {to_email} | "
            f"host={cfg['host']}:{cfg['port']} | user={cfg['user']}",
            flush=True,
        )

        if not cfg["host"] or not cfg["user"] or not cfg["password"]:
            print(
                "⚠️ [EmailService] SMTP no configurado — correo descartado. "
                f"host={cfg['host']!r} user={cfg['user']!r} password={'***' if cfg['password'] else 'VACÍA'}",
                flush=True,
            )
            logger.warning("SMTP no configurado — correo a %s descartado", to_email)
            return False

        # Construir payload MIME multipart/alternative
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["sender"]
        msg["To"] = to_email

        # Parte texto plano (siempre presente para accesibilidad)
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Parte HTML opcional
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            # Timeout de 20s (aumentado de 10s para tolerar latencia en Render cold-start)
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as server:
                server.ehlo()
                server.starttls()  # Ascenso obligatorio a túnel cifrado
                server.ehlo()
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["sender"], [to_email], msg.as_string())
            print(f"✅ [EmailService] Correo enviado exitosamente a {to_email}", flush=True)
            logger.info("Correo enviado exitosamente a %s", to_email)
            return True

        except Exception as e:
            print(f"🚨 ERROR CRÍTICO DE CORREO: {str(e)}", flush=True)
            traceback.print_exc()
            logger.error("Error crítico enviando correo a %s: %s", to_email, e)

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
