import smtplib
from email.mime.text import MIMEText
from typing import Dict, List

import mercadopago
from flask import current_app
from twilio.rest import Client


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


class TicketService:
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
