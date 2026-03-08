import logging
from typing import Dict, List

import mercadopago
from flask import current_app


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
