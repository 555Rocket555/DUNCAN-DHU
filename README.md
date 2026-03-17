# Duncan Dhu 

Plataforma full-stack de comercio electrónico y gestión operativa para restaurantes. Combina un front-end rápido y optimizado (SSR) con un back-office completo, y un Chatbot Híbrido potenciado por IA Generativa.

---

## 🚀 Características Principales

### 🛒 Para los Clientes (Public UX)
- **Catálogo Dinámico:** Navegación por categorías y productos en tiempo real.
- **Carrito de Compras:** Persistencia basada en sesión, validación de stock antes del checkout.
- **Pagos Integrados:** Soporte para compras en Efectivo y pasarela digital con **Mercado Pago**.
- **Notificaciones:** Alertas de pedido confirmado enviadas vía **WhatsApp** (Twilio).
- **Recuperación de Cuentas:** Flujo seguro de "Olvidé mi contraseña" apoyado por envío de correos transaccionales vía **SMTP/Brevo**.

### 💼 Para la Administración (Back-office)
- **Gestión de Pedidos:** Actualización de estados (Pendiente, Preparación, Completado, Cancelado) en tiempo real.
- **Punto de Venta e Inventario:** Integración de "Recetas" donde la venta de un producto (ej. Hamburguesa) descuenta automáticamente los insumos granulares del inventario (Pan, Carne).
- **Control de Productos:** Subida de imágenes procesadas y servidas instantáneamente por la CDN **Cloudinary**.
- **Reportes Mágicos:** Generación de recibos y tickets de compra en formato **PDF** (ReportLab).

### 🤖 Chatbot Híbrido (Gemini AI + FSM)
- **Máquina de Estados (FSM):** Navegación ultra-rápida por menús guiados con botones para acciones comunes (Ver Estado de Pedido, Información).
- **LLM Integrado:** Integra la API de `gemini-2.5-flash` acoplado con un patrón RAG (Retrieval-Augmented Generation).
- **Doble Personalidad (RBAC):**
  - **Usuario Estándar:** La IA lee el menú activo de la base de datos y asesora al cliente evitando alucinaciones de precios o ítems.
  - **Administrador:** La IA se transforma en un Analista de Datos, leyendo proyecciones y pedidos activos para reportar resúmenes operacionales en tiempo real.

---

## 🛠️ Stack Tecnológico

- **Backend:** Python 3.11, Flask 3.0.3 (Application Factory Pattern)
- **Base de Datos:** PostgreSQL, Flask-SQLAlchemy, Flask-Migrate, Alembic
- **Frontend:** Jinja2 (SSR), Vanilla CSS (flexbox/grid layouts fluidos), Vanilla JavaScript
- **IA:** Google Generative AI (Google Gemini 2.5 Flash)
- **Servicios Cloud:** Mercado Pago SDK, Twilio (WhatsApp), Cloudinary (Imágenes CDN), Brevo (SMTP Relay)

---

## 📦 Instalación y Despliegue Local

### Prerrequisitos
- Python 3.10 o superior (recomendado 3.11)
- PostgreSQL instalado y con un servidor corriendo en el puerto 5432.

### Paso a paso

1. **Clonar el repositorio:**
   ```bash
   git clone <url-del-repositorio>
   cd DUNCAN-DHU
   ```

2. **Crear y activar el entorno virtual:**
   ```bash
   python -m venv venv
   
   # En Windows:
   venv\Scripts\activate
   
   # En macOS/Linux:
   source venv/bin/activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar Variables de Entorno:**
   Copia el archivo base y reemplaza tus credenciales:
   ```bash
   # En Windows (Powershell):
   Copy-Item .env.example -Destination .env
   
   # En Unix (Bash): 
   cp .env.example .env
   ```
   *(Importante: Debes configurar `SECRET_KEY` y `DATABASE_URL` obligatoriamente para evitar errores de arranque)*

5. **Inicializar la Base de Datos:**
   Este script aplicará las tablas necesarias (migraciones) y creará los datos "semilla" (menú inicial y cuenta de admin).
   ```bash
   python init_db.py
   ```

6. **Correr el servidor local de desarrollo:**
   ```bash
   python wsgi.py
   ```
   🚀 El proyecto estará corriendo en `http://127.0.0.1:5000`.

---

## 🗺️ Roadmap y Próximas Tareas

El desarrollo del proyecto se mantiene activo. Las próximas implementaciones prioritarias son:

- [ ] **Webhooks de Mercado Pago Mejorados:** Añadir colas asíncronas para el procesamiento de pagos fallidos o retrasos en la respuesta de la pasarela.
- [ ] **Mejora del Carrito:** Transformar la persistencia del carrito en la sesión del servidor hacia persistencia completa en Base de Datos (para usuarios logueados).
- [ ] **Onboarding del Chatbot:** Añadir respuestas preparadas automáticas de Gemini en el primer contacto basándose en la hora del día ("¡Buenos días", "¡Buenas noches").
- [ ] **Despliegue CI/CD:** Desarrollar flujos de trabajo en GitHub Actions para pruebas automatizadas y despliegue a Render.com.
