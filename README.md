# DUNCAN-DHU

## Backend Flask

Backend en Flask para las vistas HTML existentes, con PostgreSQL, Mercado Pago, carrito, admin, API y envío de tickets.

## Requisitos
- Python 3.11+
- PostgreSQL local o una base de datos en Render

## Configuración rápida
1. Copia .env.example a .env y ajusta valores.
2. Instala dependencias:
   - pip install -r requirements.txt
3. Inicializa la base de datos:
   - flask --app app.py init-db
4. Ejecuta:
   - flask --app app.py run

## Despliegue en Render
1. Sube el repositorio a GitHub.
2. En Render: New + -> Blueprint y selecciona este repo.
3. Configura las variables de entorno en el servicio web:
   - `DATABASE_URL` (usa la DB creada por Render)
   - `BASE_URL` (la URL de tu servicio en Render)
   - `SECRET_KEY`
   - `MP_ACCESS_TOKEN`, `MP_PUBLIC_KEY`, `MP_WEBHOOK_SECRET`
   - `SMTP_*`, `TWILIO_*` si aplican
4. Despliega y espera a que el servicio inicie.

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
