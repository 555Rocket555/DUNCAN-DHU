# Duncan Dhu — Plataforma Integral de E-commerce y Gestión Operativa para Restaurantes

![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.0.3-black?style=flat-square)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-13+-336791?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## 📋 Resumen Ejecutivo

**Duncan Dhu** es una plataforma **monolítica full-stack** desarrollada en **Python/Flask** que integra un sistema de comercio electrónico B2C con un back-office administrativo completo y un chatbot híbrido potenciado por IA generativa (Google Gemini).

### Objetivos Principales

| Objetivo | Descripción |
|----------|-----------|
| **Catálogo Dinámico** | Gestión centralizada de productos, categorías e inventario granular mediante recetas (producto = combinación de insumos). |
| **Checkout Omnicanal** | Procesamiento de pagos en efectivo e integración con **Mercado Pago** (pasarela digital). |
| **Gestión Operativa** | Dashboard administrativo con control de órdenes, inventario, recetas, reportes PDF y análisis de ingresos. |
| **Notificaciones en Tiempo Real** | Alertas vía **WhatsApp** (Twilio) y email transaccional (Brevo API). |
| **Asistencia Inteligente** | Chatbot FSM (Máquina de Estados Finitos) + LLM (Google Gemini 2.5 Flash) con patrón RAG ligero desde BD. |
| **Seguridad Robusta** | Autenticación con hashing Argon2, MFA por email para admins, tokens CSRF, reCAPTCHA v2, validación de email. |

---

## 🛠️ Stack Tecnológico

### **Backend**

| Componente | Tecnología | Propósito |
|-----------|-----------|----------|
| **Framework Web** | Flask 3.0.3 | Application Factory Pattern; enrutamiento modular por blueprints. |
| **ORM & Migraciones** | SQLAlchemy 2.0.48 + Flask-SQLAlchemy 3.1.1 + Alembic 1.18.4 | Modelado de datos, relaciones y versionado de esquema. |
| **Autenticación** | Flask-Login 0.6.3 + Argon2-CFFI 23.1.0 | Gestión de sesiones, hashing seguro de contraseñas. |
| **Validación de Formularios** | Flask-WTF 1.2.1 + WTForms 3.2.1 | CSRF, validación de entrada, sanitización. |
| **Servidor WSGI** | Gunicorn 21.2.0 | Servidor de producción (recomendado para Render). |
| **Base de Datos** | PostgreSQL + Psycopg3 3.3.3 | Base de datos relacional; soporte para psycopg3. |

### **Frontend**

| Componente | Tecnología | Propósito |
|-----------|-----------|----------|
| **Template Rendering** | Jinja2 3.1.6 | SSR (Server-Side Rendering) de plantillas HTML. |
| **Estilos** | Vanilla CSS (Flexbox/Grid) | Diseño responsive, sin dependencias externas de CSS. |
| **Interactividad** | Vanilla JavaScript | AJAX para carrito, chat, notificaciones (sin frameworks pesados). |

### **Integraciones Externas**

| Servicio | Biblioteca | Uso |
|---------|-----------|-----|
| **Mercado Pago** | mercadopago 2.2.1 SDK | Procesamiento de pagos en línea; webhooks para confirmación. |
| **WhatsApp** | twilio 9.2.3 | Notificaciones de pedidos vía mensajería. |
| **Correos** | Brevo REST API (requests 2.32.5) | Email transaccional (MFA, reset password, confirmación de pedidos). |
| **Imágenes CDN** | cloudinary 1.40.0 | Almacenamiento y optimización de imágenes de productos. |
| **IA Generativa** | google-generativeai 0.8.3 | Gemini 2.5 Flash para respuestas contextuales del chatbot. |
| **Generación de PDFs** | reportlab 4.2.2 | Tickets y recibos de compra en formato PDF. |

### **Stack de Desarrollo**

- **Linting & Type Checking**: Pylance (client-side en VS Code)
- **Entorno Virtual**: Python venv / virtualenv
- **Gestor de Dependencias**: pip
- **Control de Versiones**: Git + GitHub

### **Infraestructura**

- **Hosting**: Render (o similar PaaS)
- **Despliegue**: Docker-ready (recomendado), o como aplicación web estándar
- **CI/CD**: (No implementado en el repo actual; recomendado para la rama `main`)

---

## 🏗️ Arquitectura y Patrones

### **Arquitectura General**

**Monolito Modular por Blueprints** — La aplicación Flask se divide en módulos de negocio ubicados en `app/routes/`:

```
app/
└── routes/
    ├── public.py      # Rutas públicas: catálogo, carrito, checkout, chat
    ├── auth.py        # Autenticación: login, registro, reset password, MFA
    ├── admin.py       # Back-office: dashboard, CRUD de productos, gestión de pedidos
    └── api.py         # Endpoints JSON: fetch de órdenes, chat GPT
└── services/
    ├── payment_service.py     # Orquestación de Mercado Pago
    ├── inventory_service.py   # Descuento atómico e idempotente de stock
    ├── chat_service.py        # FSM + RAG + Google Gemini
    └── ticket_service.py      # Email (Brevo) + WhatsApp (Twilio)
└── models.py          # ORM: User, Product, Category, Order, Inventory, recetas
└── config.py          # Configuración (DB, APIs externas, seguridad)
└── extensions.py      # Instancias de Flask extensions (db, migrate, login_manager, csrf)
```

**Ventajas:**
- Modularidad sin complejidad de microservicios (overhead innecesario para escala actual)
- Separación clara de responsabilidades (rutas vs. servicios vs. modelos)
- Fácil testing de lógica de negocio (servicios sin dependencies de web context)

**Limitaciones:**
- A escala de 100k+ usuarios/día, considerar desacoplar pagos, chat e inventario en microservicios o colas asincrónicas

---

### **Patrones de Diseño**

#### 1. **Application Factory Pattern** (`app/__init__.py`)
```python
def create_app():
    app = Flask(...)
    db.init_app(app)
    login_manager.init_app(app)
    # Registrar blueprints, hooks, CLI commands
    return app
```
**Objetivo:** Permitir múltiples instancias de la app con configuraciones distintas (testing, desarrollo, producción).

#### 2. **Service Layer Pattern** (`app/services/`)
Lógica de negocio encapsulada en clases estáticas (`PaymentService`, `InventoryService`, etc.) que pueden ser probadas independientemente de rutas HTTP.

#### 3. **Repository Pattern (implícito en ORM)**
SQLAlchemy actúa como abstracción de la BD; consultas centralizadas en modelos (`Product.query.filter_by(...)`)

#### 4. **Máquina de Estados Finitos (FSM)** — Chat
El chatbot navega por estados predefinidos (menú principal → ver pedido → historial) sin necesidad de IA en cada paso. Solo delega a Gemini cuando se requiere respuesta contextual o análisis.

#### 5. **Retrieval-Augmented Generation (RAG) Ligero**
El chatbot consulta la BD para:
- Validar que el usuario logueado sea propietario del pedido
- Obtener menú activo y contexto de disponibilidad
- Armar contexto para la IA (evitando alucinaciones sobre items/precios inexistentes)

---

### **Flujo de Datos Principal**

```mermaid
graph TB
    A["🌐 Navegador<br/>(Cliente)"] -->|HTTP| B["Flask<br/>public.py"]
    B -->|Renderiza| C["Jinja2 Templates<br/>+ CSS/JS"]
    A -->|Visualiza| C
    
    B -->|Query/Insert| D["SQLAlchemy ORM"]
    D -->|SQL| E["PostgreSQL"]
    E -->|Tablas| F["users, products, orders,<br/>inventory, recetas"]
    
    B -->|Procesa Pago| G["PaymentService"]
    G -->|API| H["Mercado Pago SDK"]
    H -->|Init Point URL| I["Pasarela MP"]
    A -->|Redirige| I
    I -->|Return/Webhook| B
    
    B -->|Notificación| J["TicketService"]
    J -->|REST API| K["Brevo Email<br/>+ Twilio SMS"]
    K -->|Envía| L["📧 📱 Cliente"]
    
    B -->|Descuento Stock| M["InventoryService"]
    M -->|Update| E
    
    B -->|Chat Request| N["ChatService"]
    N -->|Quick Replies| O["BD: menú, estado pedido"]
    N -->|Gemini API| P["Google Generative AI"]
    P -->|Respuesta contextual| N
    N -->|JSON| A
```

---

### **Ciclo de Una Orden** (Flujo Crítico)

#### 1. **Creación de Orden**
```
Cliente añade productos al carrito (session["cart"])
       ↓
Cliente inicia sesión y va a checkout
       ↓
Selecciona método de pago: efectivo o Mercado Pago
       ↓
Se crea Order + OrderItems en BD (status='pendiente')
```

#### 2. **Efectivo**
```
Si pago es efectivo:
  - Descuento de stock inmediatamente (InventoryService.deduct_stock)
  - Envío de ticket vía email/WhatsApp
  - Order marcada como completada (status='completado')
```

#### 3. **Mercado Pago**
```
Si pago es MP:
  - PaymentService.create_preference() genera URL de Mercado Pago
  - Cliente redirigido a init_point (pasarela)
  - Si aprueba: MP envía webhook a /mp/webhook
  - Webhook actualiza payment_status='aprobado'
  - InventoryService.deduct_stock() se ejecuta (idempotencia con stock_processed)
  - Ticket enviado al cliente
```

---

### **Evaluación de Arquitectura**

#### ✅ **Fortalezas**

1. **Modularidad sin sobrediseño:** Los blueprints permiten agregar nuevas funcionalidades sin afectar código existente.
2. **Capa de servicios clara:** Fácil testing y reutilización de lógica de negocio.
3. **ORM bien estructurado:** Relaciones OneToMany (Order ↔ OrderItems), ManyToMany (Products ↔ InventoryItems via ProductRecipe).
4. **Seguridad de sesión:** Timeout automático, CSRF tokens, Argon2 hashing, MFA para admins.
5. **Integración modular de APIs externas:** Cada servicio (email, pagos, IA) es independiente y configurable.

#### ⚠️ **Limitaciones**

1. **Single Point of Failure (Base de Datos):** PostgreSQL única sin replicación; fallo de BD = caída de la app.
2. **Sin colas asincrónicas:** Operaciones lentas (email, Gemini API) bloquean la sesión HTTP. A escala, necesitarias **Celery/RabbitMQ** o **Redis queues**.
3. **Sin cache distribuido:** Cada petición consulta BD. Implementar **Redis** para sesiones, caché de menú, rate limiting.
4. **Migraciones sin versionado en repo:** `migrations/versions` vacío; historial de esquema no materializado.
5. **Sin soft-delete coherente:** Órdenes siempre se crean; deleteos pueden quebrar relaciones.

#### 🎯 **Juicio General**

**La arquitectura es sólida para una startup de medio alcance (1k-10k usuarios activos diarios).**

Cumple bien todos los patrones SOLID básicos y es escalable horizontalmente con mínimos cambios. Si la demanda crece 10x, primero agregar colas asincrónicas y caché; después considerar desacoplar en microservicios (pagos, chat, inventario).

---

## 📦 Instalación y Configuración

### **Prerequisitos**

- **Python** 3.10+ (recomendado 3.11)
- **PostgreSQL** 13+ corriendo en puerto 5432
- **pip** (gestor de paquetes de Python)
- **Git** para clonar el repositorio

### **1. Clonar el Repositorio**

```bash
git clone https://github.com/tu-usuario/DUNCAN-DHU.git
cd DUNCAN-DHU
```

### **2. Crear y Activar Entorno Virtual**

```bash
# Crear entorno virtual
python -m venv .venv

# Activar (en Linux/macOS)
source .venv/bin/activate

# Activar (en Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activar (en Windows Command Prompt)
.venv\Scripts\activate.bat
```

### **3. Instalar Dependencias**

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### **4. Configurar Variables de Entorno**

Copia el archivo de ejemplo y edita con tus credenciales:

```bash
# En Linux/macOS
cp .env.example .env

# En Windows
copy .env.example .env
```

Edita `.env` con tus valores (usar editor de texto o terminal):

```bash
cat > .env << 'EOF'
# ═══════════════════════════════════════════════════════════════════════
# SEGURIDAD (OBLIGATORIO)
# ═══════════════════════════════════════════════════════════════════════
SECRET_KEY=tu_clave_secreta_muy_larga_32_caracteres_minimo
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/duncan_dhu

# ═══════════════════════════════════════════════════════════════════════
# MERCADO PAGO
# ═══════════════════════════════════════════════════════════════════════
MP_ACCESS_TOKEN=TEST-1234567890abcdef...
MP_PUBLIC_KEY=TEST-1234567890abcdef...
MP_WEBHOOK_SECRET=tu_webhook_secret_opcional_para_validacion

# ═══════════════════════════════════════════════════════════════════════
# CLOUDINARY (CDN de Imágenes)
# ═══════════════════════════════════════════════════════════════════════
CLOUDINARY_CLOUD_NAME=tu_cloud_name
CLOUDINARY_API_KEY=tu_api_key
CLOUDINARY_API_SECRET=tu_api_secret

# ═══════════════════════════════════════════════════════════════════════
# EMAIL (Brevo REST API)
# ═══════════════════════════════════════════════════════════════════════
BREVO_API_KEY=xkeysib-abcdef1234567890...
SMTP_FROM=no-reply@duncandhu.com

# ═══════════════════════════════════════════════════════════════════════
# WHATSAPP (Twilio)
# ═══════════════════════════════════════════════════════════════════════
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+1234567890

# ═══════════════════════════════════════════════════════════════════════
# IA GENERATIVA (Google Gemini)
# ═══════════════════════════════════════════════════════════════════════
GEMINI_API_KEY=AIzaSy...

# ═══════════════════════════════════════════════════════════════════════
# RECAPTCHA v2 (Protección ante bots)
# ═══════════════════════════════════════════════════════════════════════
RECAPTCHA_SITE_KEY=6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ...
RECAPTCHA_SECRET_KEY=6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4...

# ═══════════════════════════════════════════════════════════════════════
# REDES SOCIALES & UBICACIÓN
# ═══════════════════════════════════════════════════════════════════════
SOCIAL_FACEBOOK=https://www.facebook.com/tucuenta
SOCIAL_INSTAGRAM=https://www.instagram.com/tucuenta
SOCIAL_TIKTOK=https://www.tiktok.com/@tucuenta
GOOGLE_MAPS_URL=https://www.google.com/maps/embed?...

# ═══════════════════════════════════════════════════════════════════════
# CREDENCIALES ADMIN (seed en init_db.py)
# ═══════════════════════════════════════════════════════════════════════
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

# ═══════════════════════════════════════════════════════════════════════
# PRODUCCIÓN (Render, Heroku, etc.)
# ═══════════════════════════════════════════════════════════════════════
BASE_URL=http://localhost:5000  # Cambiar a https://tu-dominio.com en prod
PYTHON_VERSION=3.11.6

EOF
```

**Notas Importantes:**
- `SECRET_KEY`: Generar con `python -c "import secrets; print(secrets.token_hex(32))"`
- `DATABASE_URL`: Debe ser una URL válida de PostgreSQL (psycopg3)
- Servicios opcionales (Brevo, Twilio, Cloudinary, Gemini): Si no están configurados, la app funcionará en modo degradado (sin email, sin chat IA, sin images CDN)

### **5. Inicializar Base de Datos**

```bash
# Crear tablas y datos por defecto (admin + Menu seed)
python init_db.py

# Alternativa: usando CLI de Flask
flask init-db

# (Opcional) Agregar productos gourmet extendidos
flask seed-extended

# (Opcional) Populan las recetas (product_recipes)
flask seed-recipes
```

**Qué hace `init_db.py`:**
1. Aplica migraciones Alembic pendientes
2. Crea todas las tablas (`products`, `users`, `orders`, etc.)
3. Crea usuario admin con credenciales de `.env`
4. Popula las categorías y menú inicial

### **6. Ejecutar Servidor Local**

```bash
# Desarrollo (con reloader automático)
python wsgi.py

# O con Flask CLI
flask run

# O específicamente en puerto 5000
python wsgi.py 5000
```

Accede a **`http://localhost:5000`** en tu navegador.

### **7. Para Producción (Render)**

1. Conecta tu repositorio de GitHub a Render
2. Render detectará `render.yaml` y configurará automáticamente
3. Las variables de entorno se configuran en el panel de Render
4. El despliegue ejecuta `init_db.py` antes de iniciar el servidor

```yaml
# render.yaml (ya está configurado en el repo)
services:
  - type: web
    name: duncan-dhu
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn wsgi:app
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.6
      - key: SECRET_KEY
        generateValue: true
```

### **8. Validar la Instalación**

```bash
# Listar rutas disponibles
flask routes

# Ejecutar tests básicos
pytest tests/

# Verificar conectividad a BD
python -c "from app import create_app; app = create_app(); print('✅ App creada exitosamente')"
```

---

## 🗂️ Estructura del Proyecto

```
DUNCAN-DHU/
│
├── 📄 README.md                          # Documentación principal (este archivo)
├── 📄 DOCUMENTATION.md                   # Documentación técnica detallada
├── 📄 context.md                         # Análisis contextual (notas de desarrollo)
├── 📄 requirements.txt                   # Dependencias Python (pip)
├── 📄 pyrightconfig.json                 # Configuración de type checking (Pylance)
├── 📄 render.yaml                        # Configuración de despliegue en Render
├── 📄 setup_prod.py                      # Script de setup para producción
├── 📄 init_db.py                         # Inicialización de BD
├── 📄 .env.example                       # Plantilla de variables de entorno
├── 📄 .gitignore                         # Git: archivos ignorados
│
├── 📁 app/                               # Raíz de la aplicación Flask
│   ├── 📄 __init__.py                    # Application Factory (crear instancia de Flask)
│   ├── 📄 config.py                      # Configuración centralizada (DB, APIs, seguridad)
│   ├── 📄 extensions.py                  # Instancias de extensiones Flask (db, migrate, auth)
│   ├── 📄 models.py                      # ORM: User, Product, Order, Inventory, recetas
│   │
│   ├── 📁 routes/                        # Blueprints (módulos de rutas)
│   │   ├── 📄 public.py                  # Rutas públicas (catálogo, carrito, chat, checkout)
│   │   ├── 📄 auth.py                    # Autenticación (login, registro, reset password, MFA)
│   │   ├── 📄 admin.py                   # Back-office (dashboard, CRUD, gestión de órdenes)
│   │   └── 📄 api.py                     # APIs JSON (fetch órdenes, chat GPT, webhooks)
│   │
│   └── 📁 services/                      # Capa de servicios (lógica de negocio)
│       ├── 📄 __init__.py                # Exports de servicios
│       ├── 📄 payment_service.py         # Orquestación de Mercado Pago (crear preferencias)
│       ├── 📄 inventory_service.py       # Descuento atómico e idempotente de stock
│       ├── 📄 ticket_service.py          # Email (Brevo API) + WhatsApp (Twilio)
│       └── 📄 chat_service.py            # FSM + RAG + Google Gemini (chatbot)
│
├── 📁 templates/                         # Plantillas Jinja2 (HTML renderizado en servidor)
│   ├── 📄 base.html                      # Plantilla base (header, footer, nav)
│   ├── 📄 admin-base.html                # Plantilla base del back-office
│   ├── 📄 Principal.html                 # Página de inicio (home)
│   ├── 📄 productos-usuarios.html        # Catálogo público
│   ├── 📄 carrito-compras-usuarios.html  # Vista del carrito
│   ├── 📄 login.html                     # Formulario de login
│   ├── 📄 registro-usuarios.html         # Formulario de registro
│   ├── 📄 efectivo-usuario.html          # Checkout con efectivo
│   ├── 📄 metodo-pago-usuarios.html      # Selector de método de pago
│   ├── 📄 ticket-tarjeta.html            # Recibo de orden (imprimible)
│   ├── 📄 login-admin.html               # Login de administrador
│   ├── 📄 dashboard-admin.html           # Dashboard administrativo
│   ├── 📄 admin-productos.html           # Gestión de productos
│   ├── 📄 admin-inventario.html          # Gestión de inventario
│   ├── 📄 admin-receta.html              # Gestión de recetas (producto ↔ insumo)
│   ├── 📄 admin-ordenes.html             # Gestión de órdenes
│   ├── 📄 admin-usuarios.html            # Gestión de usuarios
│   ├── 📄 admin-reportes.html            # Reportes PDF (ingresos, inventario)
│   ├── 📄 macros.html                    # Macros Jinja2 reutilizables
│   │
│   ├── 📁 auth/                          # Plantillas de autenticación
│   │   ├── 📄 login.html                 # Login
│   │   ├── 📄 mfa_verify.html            # Verificación MFA (código OTP por email)
│   │   ├── 📄 forgot_password.html       # Recuperación de contraseña
│   │   ├── 📄 reset_password.html        # Reset de contraseña (con token)
│   │   └── 📄 email_verification_pending.html # Verificación de email pendiente
│   │
│   ├── 📁 public/                        # Plantillas públicas
│   │   ├── 📄 categoria.html             # Catálogo por categoría
│   │   ├── 📄 mis_pedidos.html           # Historial de pedidos del usuario
│   │   ├── 📄 perfil.html                # Perfil del usuario
│   │   ├── 📄 politica-privacidad.html   # Página de privacidad
│   │   ├── 📄 terminos.html              # Página de términos y condiciones
│   │   └── 📁 components/
│   │       └── 📄 _product_card.html     # Componente: tarjeta de producto (reutilizable)
│   │
│   ├── 📁 components/                    # Componentes compartidos
│   │   └── 📄 _chatbot.html              # Widget del chatbot (FSM + entrada de mensajes)
│   │
│   ├── 📄 contactanos.html               # Página de contacto
│   └── 📄 macros.html                    # Macros/helpers de Jinja2
│
├── 📁 static/                            # Archivos estáticos (CSS, JS, imágenes)
│   ├── 📁 css/
│   │   └── 📄 main.css                   # Estilos principales (flexbox/grid, responsive)
│   │
│   ├── 📁 img/                           # Imágenes locales (logo, iconos)
│   │
│   └── 📁 js/                            # JavaScript client-side
│       ├── 📄 cart.js                    # Lógica del carrito (AJAX)
│       ├── 📄 chat.js                    # Interacción con chatbot (WebSocket o polling)
│       └── 📄 forms.js                   # Validación de formularios (client-side)
│
├── 📁 migrations/                        # Alembic: versionado de esquema BD
│   ├── 📄 alembic.ini                    # Configuración de Alembic
│   ├── 📄 env.py                         # Script de migración automática
│   ├── 📄 script.py.mako                 # Template de migración
│   ├── 📄 README                         # Instrucciones de migraciones
│   │
│   └── 📁 versions/                      # Historial de revisiones de esquema
│       └── 📄 0f9b759210fb_add_email_verification_fields_to_user_.py  # Ejemplo: agregar campos email_verified, email_verified_at
│
├── 📁 tests/                             # Pruebas unitarias e integración
│   └── 📄 test_chatbot_api.py            # Tests básicos del endpoint chatbot
│
├── 📄 wsgi.py                            # Entry point WSGI (Gunicorn, servidor de producción)
└── 📄 .venv/                             # Entorno virtual (ignorado por Git)

---

### **Descripciones Técnicas por Archivo Principal**

| Archivo | Tipo | Descripción |
|---------|------|-----------|
| `app/__init__.py` | Backend | Application Factory; inicializa extensiones (db, login, csrf); registra blueprints; define hooks de sesión y caché. |
| `app/config.py` | Backend | Configuración centralizada: DB URL, claves API, timeouts, admin seed. Valida obligatoriedad de `SECRET_KEY` y `DATABASE_URL`. |
| `app/extensions.py` | Backend | Instancias de SQLAlchemy, Flask-Login, Flask-Migrate, CSRF (inicializadas sin app, luego vinculadas en factory). |
| `app/models.py` | Backend (ORM) | Modelos SQLAlchemy: User, Product, Category, Order, InventoryItem, ProductRecipe (recetas). Relaciones y métodos de validación. |
| `app/routes/public.py` | Backend | Rutas HTTP públicas: home, catálogo, carrito (sesión), checkout, tickets, chat FSM, webhooks MP, mis pedidos. |
| `app/routes/auth.py` | Backend | Autenticación: login (con MFA para admins), registro, logout, reset password con tokens, email verification. reCAPTCHA integrado. |
| `app/routes/admin.py` | Backend | Back-office: dashboard, CRUD de productos (con Cloudinary), gestión de inventario, recetas, órdenes, usuarios, reportes PDF. |
| `app/routes/api.py` | Backend (API REST) | Endpoints JSON: `GET /api/products`, `POST /api/chat`, `GET /api/orders/<id>`, `POST /mp/webhook` (incluye validación de firma). |
| `app/services/payment_service.py` | Backend | Capa de servicios para Mercado Pago: crear preferencias, manejar webhooks. |
| `app/services/inventory_service.py` | Backend | Descuento atómico e idempotente de inventario (`deduct_stock`); valida stock previa, actualiza, maneja rollback. |
| `app/services/ticket_service.py` | Backend | Email (Brevo REST API) + WhatsApp (Twilio): envío de confirmación, MFA, reset password; detecta disponibilidad. |
| `app/services/chat_service.py` | Backend (IA) | Chatbot: FSM (máquina de estados) + RAG (contexto de BD) + Google Gemini 2.5 Flash. Respuestas predefinidas (QUICK_REPLIES). |
| `templates/base.html` | Frontend (Template) | Plantilla base Jinja2: header, footer, nav responsive, carrito, widget de chat. |
| `templates/Principal.html` | Frontend | Home: hero, destacados de productos, CTA (Call To Action), integración de ubicación y redes. |
| `templates/productos-usuarios.html` | Frontend | Catálogo público: grilla de productos, filtros por categoría, búsqueda, carrito flotante. |
| `templates/carrito-compras-usuarios.html` | Frontend | Vista del carrito: items, totales, descuentos (si aplica), botones de checkout. |
| `templates/login.html` | Frontend | Formulario de login: usuario/email + contraseña + reCAPTCHA; diferencia admin vs. cliente. |
| `templates/admin-base.html` | Frontend | Plantilla base del back-office: sidebar de navegación, header con usuario logged, footer. |
| `templates/dashboard-admin.html` | Frontend | KPIs: órdenes hoy, ingresos, productos, stock bajo. Gráficos (Chart.js, D3, etc.) si aplica. |
| `static/css/main.css` | Frontend | Estilos CSS: flexbox/grid responsive, tema de colores, animaciones; sin dependencias externas (Bootstrap descartado). |
| `init_db.py` | DevOps | Script: crea tablas, aplica migraciones Alembic, seed de datos (admin, categorías, productos iniciales). |
| `wsgi.py` | DevOps/Backend | Entry point WSGI: instancia la app Flask. Render/Gunicorn apunta aquí (`gunicorn wsgi:app`). |
| `render.yaml` | DevOps | Configuración de despliegue en Render: buildCommand, startCommand, envVars autogeneradas (SECRET_KEY). |
| `requirements.txt` | DevOps | Listado de dependencias Python con pinned versions (reproducibilidad). |
| `pyrightconfig.json` | DevOps (Dev) | Configuración de Pylance (type checking en VS Code): strict mode, exclusiones. |
| `migrations/alembic.ini` | DevOps (DB) | Configuración de Alembic: dirección de migraciones, template SQL. |
| `migrations/env.py` | DevOps (DB) | Script automático que ejecuta migraciones en desarrollo y producción. |

---

## 📊 Flujo de Datos (Data Flow)

### **1. Flujo de Catálogo (Browse Products)**

```
Cliente abre navegador
    ↓
GET / (home)
    ↓
Flask renderiza Principal.html
    ↓
Jinja2 query: Product.query.filter_by(active=True).limit(4)
    ↓
SQLAlchemy traduce a SQL SELECT
    ↓
PostgreSQL retorna 4 productos populares
    ↓
Plantilla renderiza HTML con imágenes (Cloudinary URLs)
    ↓
Navegador descarga CSS, JS, imágenes
    ↓
Usuario ve home con productos destacados
```

**Optimizaciones:**
- Cache de sesión para menú
- Índices en `active`, `category_id` en tabla `products`
- CDN (Cloudinary) para imágenes

---

### **2. Flujo de Carrito (Add to Cart)**

```
Cliente hace clic "Pedir" en producto
    ↓
JavaScript AJAX: POST /carrito/agregar/123
    ↓
Flask: validar producto existe y tiene stock
    ↓
Si válido: session["cart"]["123"] += 1
    ↓
session.modified = True (Flask marca para guardar)
    ↓
Cookie de sesión encriptada se guarda en navegador
    ↓
JavaScript actualiza contador de carrito (DOM)
    ↓
Cliente ve "✅ Agregado al carrito" (toast)
```

**Implementación:**
- Carrito vive en **servidor HTTP (session)**, no en BD
- Ventaja: rápido, sin DB query
- Desventaja: se pierde si el usuario limpia cookies o usa otro dispositivo
- **Mejora futura:** guardar carrito en BD para usuarios autenticados

---

### **3. Flujo de Checkout con Efectivo**

```
Cliente hace clic "Proceder al Pago"
    ↓
Validar usuario autenticado (login_required)
    ↓
GET /efectivo-usuario → renderiza resumen
    ↓
Usuario confirma "Pagar en Efectivo"
    ↓
POST /efectivo-usuario
    ↓
Flask:
  1. Crea Order (status='pendiente', payment_method='efectivo')
  2. Crea OrderItems desde session["cart"]
  3. Calcula total
  4. Commit a BD
    ↓
InventoryService.deduct_stock(order):
  - Itera productos en Order
  - Para cada producto: obtiene recetas (ProductRecipe)
  - Descuenta insumos granulares del inventario
  - Valida stock >= cantidad requerida
  - Si error: rollback
    ↓
TicketService.send_email():
  - Obtiene credenciales de config
  - Construye HTML del ticket
  - POST a Brevo API con credenciales
    ↓
TicketService.send_whatsapp():
  - Obtiene Twilio credentials
  - Envía mensaje via Twilio SMS/WhatsApp
    ↓
Limpia session["cart"]
    ↓
Redirige a /ticket-tarjeta
    ↓
Renderiza recibo (imprimible)
```

**Detalles Críticos:**
- Si falla InventoryService → rollback PERO la Order ya está en BD (bug potencial; ver Deuda Técnica)
- Email no bloqueante en futuro (cola asincrónica recomendada)

---

### **4. Flujo de Checkout con Mercado Pago**

```
Cliente selecciona "Pagar con Mercado Pago"
    ↓
POST /mercadopago-usuario
    ↓
Flask:
  1. Crea Order (status='pendiente', payment_method='mercadopago')
  2. Crea OrderItems
  3. commit()  ← ⚠️ La orden YA ESTÁ EN BD
    ↓
PaymentService.create_preference():
  - MP SDK: construye lista de items
  - external_reference = order.id
  - back_urls: success, failure
  - notification_url: /mp/webhook
  - API Mercado Pago responde con init_point (URL de pasarela)
    ↓
Si error en API MP:
  - db.session.rollback() ← DESPUÉS de commit ❌ No elimina la orden
  - Redirige con flash error
    ↓
Redirige a init_point (pasarela MP)
    ↓
Cliente autoriza pago
    ↓
MP redirige a /mp/return (success/failure)
    ↓
Flask valida status, establece payment_status
    ↓
Mientras tanto: MP envía webhook a /mp/webhook
    ↓
Webhook endpoint valida firma (HMAC-SHA256)
    ↓
Si válido: actualiza Order payment_status='aprobado'
    ↓
InventoryService.deduct_stock(order) ← Idempotente (stock_processed flag)
    ↓
Ticket enviado
    ↓
OK
```

**Problemas Detectados (Deuda Técnica):**
- ⚠️ `commit()` antes de tener `init_point` crea órdenes huérfanas si MP API falla
- Solución: usar transacción o hacer rollback + delete(order)

---

### **5. Flujo de Chat (Chatbot)**

```
Usuario tipi mensaje en widget de chat
    ↓
JavaScript captura y envía AJAX:
POST /api/bot/message
  OR
POST /api/chat (si es mensaje libre con IA)
    ↓
Si es ruta FSM (/api/bot/...):
  - ChatService._get_quick_reply(message)
  - Busca palabras clave en mensaje
  - Si match en QUICK_REPLIES → retorna respuesta predefinida
  - Si "ver pedido" → valida autenticación
  - Consulta BD: Order.query.filter_by(user_id=...)
  - Retorna JSON con estado del pedido
    ↓
Si es POST /api/chat (mensaje libre):
  - ChatService.process_message(message, user)
  - Intenta quick_reply primero (intercepta 80% de casos)
  - Si no hay match: usa Google Gemini API
  - Construye contexto RAG:
    * Menú activo (productos disponibles)
    * Estado de pedidos si el usuario está autenticado
    * Instrucciones del rol (cliente vs. admin)
  - Envía a Gemini: "Contexto: [...]. Pregunta del usuario: [...]"
  - Recibe respuesta generativa
  - Retorna JSON: { response, quick_replies: [...] }
    ↓
JavaScript renderiza mensaje en chat
    ↓
Si hay quick_replies: muestra botones de opciones
    ↓
Ciclo se repite
```

**Ventajas:**
- **FSM primero**: 80% de queries resueltas sin IA (rápido, sin latencia)
- **RAG ligero**: Gemini recibe contexto actualizado (evita alucinaciones de precios/items)
- **RBAC**: Admins obtienen otra personalidad (analista de datos)

---

### **6. Flujo de Admin (Product Management)**

```
Admin inicia sesión
    ↓
Flask valida credenciales + MFA (email OTP)
    ↓
Redirige a /admin/dashboard
    ↓
GET /admin/dashboard
    ↓
Jinja2 calcula KPIs:
  - Órdenes hoy: COUNT(orders WHERE date(created_at)=today)
  - Ingresos: SUM(orders.total WHERE date(created_at)=today)
  - Productos totales: COUNT(products)
  - Stock bajo: COUNT(inventory WHERE current <= min)
    ↓
Renderiza dashboard.html con gráficos
    ↓
Admin navega a /admin/productos
    ↓
GET /admin/productos
    ↓
Jinja2 lista: Product.query.all()
    ↓
Admin añade nuevo producto:
POST /admin/productos
  - Formulario: nombre, categoría, precio, descripción, imagen
  - request.files["image_file"] → Cloudinary uploader
  - Retorna secure_url
  - Crea Product + commit()
    ↓
Admin edita inventario:
POST /admin/inventario/edit
  - Actualiza InventoryItem.stock_current
  - Commit()
    ↓
Admin define receta (producto = X+Y+Z insumos):
POST /admin/receta/add
  - Crea ProductRecipe(product_id, inventory_item_id, quantity_required)
  - Asocia insumos granulares al producto
    ↓
Admin ve órdenes + estados:
GET /admin/ordenes
    ↓
Admin actualiza estado de orden:
POST /admin/ordenes/<id>/estado
  - Cambia status: 'pendiente' → 'preparacion' → 'completado'
  - Notifica al cliente vía WhatsApp (si email no disponible)
    ↓
Admin genera reportes PDF:
POST /admin/reportes/pdf
  - ReportLab genera PDF con tabla de ingresos/inventario
  - Retorna archivo descargable
```

---

## 🎯 Resumen Ejecutivo de Flujos

| Flujo | Actores | Tiempo Esperado | Críticidad | Dependencias |
|-------|---------|------------------|-----------|--------------|
| Browse Products | Cliente | <500ms | Media | DB índices, CDN |
| Add to Cart | Cliente | <200ms | Alta | Session, validación |
| Checkout Efectivo | Cliente + Admin | 2-5s | Crítica | DB, Email, WhatsApp |
| Checkout MP | Cliente + Mercado Pago | 5-10s | Crítica | MP API, Webhook |
| Chatbot FSM | Cliente | <300ms | Media | Cache, BD queries |
| Chatbot + Gemini | Cliente | 2-5s | Baja | Google API, latencia red |
| Admin Dashboard | Admin | <1s | Media | DB agregaciones |
| Admin CRUD | Admin | <500ms | Media | DB, Cloudinary |
| Reportes PDF | Admin | 1-3s | Baja | ReportLab, datos |

---
