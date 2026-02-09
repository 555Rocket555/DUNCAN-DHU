# DUNCAN-DHU

## Backend Flask

Backend en Flask para las vistas HTML existentes, con PostgreSQL, Mercado Pago, carrito, admin, API y envío de tickets.

## Requisitos
- Python 3.11+
- PostgreSQL local o Docker

## Configuración rápida
1. Copia .env.example a .env y ajusta valores.
2. Instala dependencias:
   - pip install -r requirements.txt
3. Inicializa la base de datos:
   - flask --app app.py init-db
4. Ejecuta:
   - flask --app app.py run

## Docker
- docker compose up --build

## Endpoints principales
- / (Home)
- /catalogo
- /catalogo/<categoria>
- /carrito
- /checkout
- /admin
- /api/products
- /api/orders/<id>

## Mercado Pago
Configura MP_ACCESS_TOKEN y MP_PUBLIC_KEY en .env.

## Tickets
- WhatsApp (Twilio): configura TWILIO_* en .env
- Correo (SMTP): configura SMTP_* en .env
