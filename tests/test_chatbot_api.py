import os
import sys

import pytest

# make sure app package can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app, db


@pytest.fixture
def app():
    # configure app for testing
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )

    with app.app_context():
        db.create_all()
        # optionally seed minimal data
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_bot_products_empty(client):
    # no products present should return message and fallback option
    resp = client.get("/api/bot/products")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body, dict)
    assert "message" in body
    assert "options" in body
    assert len(body["options"]) >= 1


def test_bot_order_status_not_logged(client):
    resp = client.get("/api/bot/order_status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "Necesitas iniciar sesión" in body.get("message", "")
    # must provide login action
    opts = body.get("options", [])
    assert any("Iniciar Sesión" in o.get("text", "") or o.get("isLink") for o in opts)
