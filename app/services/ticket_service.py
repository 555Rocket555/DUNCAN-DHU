import smtplib
from email.mime.text import MIMEText

from flask import current_app
from twilio.rest import Client

from app.models import Order


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
