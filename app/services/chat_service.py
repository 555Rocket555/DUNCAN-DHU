"""Servicio de chat — DuncanBot con Google Gemini y patrón RAG básico.

Arquitectura:
  - _get_quick_reply(): intercepta preguntas frecuentes con respuestas
    predefinidas (reglas de palabras clave). Evita llamadas a Gemini para
    saludos, horarios, ubicación, menú. Protege consultas de pedidos
    exigiendo autenticación.
  - _build_menu_context(): RAG — consulta la BD para obtener el menú activo.
  - process_message(): orquesta quick reply → Gemini fallback.

Respuestas predefinidas (QUICK_REPLIES):
  Edita el diccionario QUICK_REPLIES al final de este archivo para
  ajustar los mensajes sin tocar la lógica de detección.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import func

from flask import current_app
from flask_login import current_user

from app.models import Product, Category, Order  # noqa: F401
from app.extensions import db

logger = logging.getLogger(__name__)


# ===========================================================================
# ██████╗ ██╗   ██╗██╗ ██████╗██╗  ██╗    ██████╗ ███████╗██████╗ ██╗     ██╗   ██╗
# ██╔══██╗██║   ██║██║██╔════╝██║ ██╔╝    ██╔══██╗██╔════╝██╔══██╗██║     ╚██╗ ██╔╝
# ██████╔╝██║   ██║██║██║     █████╔╝     ██████╔╝█████╗  ██████╔╝██║      ╚████╔╝
# ██╔══██╗██║   ██║██║██║     ██╔═██╗     ██╔══██╗██╔══╝  ██╔═══╝ ██║       ╚██╔╝
# ██║  ██║╚██████╔╝██║╚██████╗██║  ██╗    ██║  ██║███████╗██║     ███████╗   ██║
# ╚═╝  ╚═╝ ╚═════╝ ╚═╝ ╚═════╝╚═╝  ╚═╝    ╚═╝  ╚═╝╚══════╝╚═╝     ╚══════╝   ╚═╝
#
# MENSAJES PREDEFINIDOS — edita aquí sin tocar la lógica de detección
# ===========================================================================
QUICK_REPLIES: dict[str, str] = {
    # Saludos
    "saludo": (
        "¡Hola! Bienvenido a Duncan Dhu 🍔 "
        "¿En qué te puedo ayudar hoy? Puedes preguntarme sobre nuestro menú, "
        "horarios, ubicación o el estado de tu pedido."
    ),
    # Horarios
    "horarios": (
        "🕒 Nuestro horario de atención es de lunes a domingo, "
        "de 12:00 PM a 10:00 PM. ¡Te esperamos!"
    ),
    # Ubicación
    "ubicacion": (
        "📍 Nos encontramos en Calle Principal #123, Centro. "
        "¡Ven a visitarnos o haz tu pedido en línea!"
    ),
    # Menú general
    "menu": (
        "🍔 Tenemos hamburguesas, snacks y bebidas que te van a encantar. "
        "Puedes ver nuestro menú completo haciendo clic en el botón de abajo."
    ),
    # Precios
    "precio": (
        "💰 Nuestros precios varían según el producto. "
        "Te invito a revisar el menú completo para ver todos los precios. "
        "¡Tenemos opciones para todos los presupuestos!"
    ),
    # Métodos de pago
    "pago": (
        "💳 Aceptamos pago en efectivo y con tarjeta a través de Mercado Pago. "
        "Elige el que más te convenga al momento de hacer tu pedido."
    ),
    # Pedidos (no autenticado)
    "pedido_guest": (
        "🔐 Para consultar el estado de tu pedido necesito verificar tu identidad. "
        "Por favor, inicia sesión y podrás ver todos tus pedidos desde 'Mis Pedidos'."
    ),
    # Pedido no encontrado (autenticado)
    "pedido_no_encontrado": (
        "🔍 No encontré un pedido con ese número en tu cuenta. "
        "Revisa el número de pedido en tu confirmación o ve a 'Mis Pedidos'."
    ),
}

# Palabras clave por intención (listas editables)
_KEYWORDS: dict[str, list[str]] = {
    "saludo":    ["hola","holaa", "holaaa", "buenas", "saludos", "hey", "hi", "buen día", "buenos días",
                  "buenas tardes", "buenas noches", "qué tal", "que tal"],
    "horarios":  ["horario", "horarios", "hora", "horas", "abre", "cierra", "abierto",
                  "open", "cuando abren", "a qué hora", "turno"],
    "ubicacion": ["ubicación", "ubi","ubicacion", "dirección", "direccion", "donde", "están",
                  "estan", "encuentran", "lugar", "domicilio", "calle", "mapa", "maps"],
    "menu":      ["menú", "menuu", "menu", "carta", "platillo", "platillos", "opciones",
                  "que tienen", "comida", "hamburguesas"],
    "precio":    ["precio", "precios", "cuánto", "cuanto", "cuesta", "cuestan", "costo",
                  "cobran", "valen"],
    "pago":      ["metodo", "metodos", "metodos de pago", "forma de pago",
                  "pago", "pagos", "pagar", "efectivo", "tarjeta",
                  "mercado pago", "mercadopago", "transferencia",
                  "como pago", "cómo pago"],
    "pedido":    ["pedido", "orden", "order", "pedí", "pedi", "compré", "compre",
                  "estado de mi pedido", "mi orden", "dónde está", "donde esta",
                  "llegó", "llego", "envío", "envio"],
}


# ===========================================================================
# Helpers internos
# ===========================================================================

def _build_menu_context() -> str:
    """Obtiene los productos activos de la BD y los formatea como texto plano.

    El texto resultante se incrusta en el system_instruction de Gemini como
    la fuente de verdad del menú para el patrón RAG.
    """
    try:
        products = (
            Product.query
            .filter_by(active=True)
            .order_by(Product.category_id, Product.name)
            .all()
        )

        if not products:
            return "El menú aún no tiene productos registrados."

        by_category: dict[str, list[Product]] = {}
        for p in products:
            cat_name = p.category.name if p.category else "Sin categoría"
            by_category.setdefault(cat_name, []).append(p)

        lines: list[str] = []
        for cat, items in by_category.items():
            lines.append(f"\n[{cat.upper()}]")
            for item in items:
                desc = f" — {item.description}" if item.description else ""
                lines.append(f"  • {item.name}: ${float(item.price):.2f}{desc}")

        return "\n".join(lines)

    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("ChatService: no se pudo leer el menú de la BD: %s", exc)
        return "(Menú temporalmente no disponible)"


def _sanitize_markdown(text: str) -> str:
    """Elimina Markdown residual que Gemini pueda generar a pesar del prompt."""
    text = re.sub(r"\*(?!\*)(.*?)\*(?!\*)", r"\1", text)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _detect_order_number(text: str) -> int | None:
    """Extrae el primer número de 1-6 dígitos del texto (posible ID de pedido)."""
    match = re.search(r"\b(\d{1,6})\b", text)
    return int(match.group(1)) if match else None


# ===========================================================================
# NLU LOCAL — Capa 2: detección de producto desde BD
# ===========================================================================

# Palabras que indican que el usuario quiere modificar el producto
_MODIFICATION_WORDS: list[str] = [
    "sin", "extra", "con extra", "doble", "más", "mas", "menos",
    "aparte", "al lado", "sin cebolla", "sin chile", "bien cocido",
    "término", "termino",
]


def _normalize(s: str) -> str:
    """Elimina acentos y normaliza a minúsculas para comparación robusta."""
    import unicodedata
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


def _detect_product_intent(msg: str) -> dict | None:
    """
    Busca nombres de productos activos de la BD en el mensaje del usuario.

    - Compara sin acentos ni mayúsculas.
    - Detecta si el usuario pidió una modificación (sin/extra/doble...)
      y advierte explícitamente que el chat no puede procesarla.
    - Devuelve un botón de acción por cada producto encontrado.
    - NO agrega nada al carrito de forma automática.

    Returns:
        dict { reply, status, options } o None si no hay match.
    """
    msg_normalized = _normalize(msg)

    try:
        products = Product.query.filter_by(active=True).all()
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("NLU: no se pudo consultar productos: %s", exc)
        return None

    # Ordenar por longitud desc: evitar que "hot" matchee antes que "hot dog"
    products.sort(key=lambda p: len(p.name), reverse=True)

    # Palabras cortas que no son significativas para el match parcial
    _STOP_WORDS = {"de", "la", "el", "los", "las", "del", "un", "una", "y", "o", "con", "sin"}

    def _significant_words(name: str) -> list[str]:
        """Filtra stop-words y retorna las palabras significativas del nombre."""
        return [w for w in _normalize(name).split() if w not in _STOP_WORDS and len(w) > 2]

    msg_words = set(msg_normalized.split())

    matched: list[Product] = []
    for p in products:
        sig_words = _significant_words(p.name)
        if not sig_words:
            continue
        # Match exacto del nombre completo (prioritario)
        if _normalize(p.name) in msg_normalized:
            matched.append(p)
            continue
        # Match parcial: al menos 2 palabras significativas en el mensaje
        # (o 1 si el nombre solo tiene 1 palabra significativa)
        hits = sum(1 for w in sig_words if w in msg_words)
        # Para nombres de 2 palabras se exigen AMBAS (evita que 'truffle'
        # matchee tanto Truffle Street como Truffle Fries).
        # Para nombres de 3+ palabras basta con n-1 palabras significativas.
        if len(sig_words) <= 2:
            threshold = len(sig_words)           # 2/2 o 1/1
        else:
            threshold = max(2, len(sig_words) - 1)  # p.ej. 2/3
        if hits >= threshold:
            matched.append(p)

    # ← Guard crítico: sin match no responder (evita "menú: ." con nombre vacío)
    if not matched:
        return None

    # Detectar palabras de modificación en el mensaje original
    has_modification = any(w in msg.lower() for w in _MODIFICATION_WORDS)

    # Construir un botón por cada producto encontrado
    options = [
        {
            "text": f"➕ Agregar {p.name} (${float(p.price):.2f})",
            "mutationHookUrl": f"/carrito/agregar/{p.id}",
            "requiresAuth": True,
            "style": "primary",
        }
        for p in matched
    ]
    options.append({"text": "📖 Ver todas las opciones", "next": "menu", "style": "outline"})

    nombres = ", ".join(p.name for p in matched)

    if has_modification:
        reply = (
            f"🔍 Encontré en nuestro menú: {nombres}.\n\n"
            "Recuerda que el chat no puede aplicar modificaciones al producto — "
            "se agregará con su receta original. "
            "¿Deseas agregarlo de todas formas?"
        )
    else:
        reply = f"🔍 Encontré esto en nuestro menú: {nombres}. ¿Lo agrego a tu carrito?"

    logger.info("NLU product match: %s | modificación: %s", nombres, has_modification)
    return {"reply": reply, "status": "ok", "options": options}


# ===========================================================================
# NLU LOCAL — Capa 3: clasificador de intención por puntuación
# ===========================================================================

# Pesos por intención (editable sin tocar la lógica)
_INTENT_WEIGHTS: dict[str, dict[str, float]] = {
    "compra": {
        "quiero": 1.5, "dame": 1.5, "pide": 1.2, "pedir": 1.2,
        "me das": 2.0, "agrega": 2.0, "agrego": 1.5,
        "añade": 2.0, "añadir": 2.0, "añademe": 2.0,
        "ordena": 1.5, "orden": 1.0, "quiero pedir": 2.5,
        "ponme": 1.5, "trae": 1.5, "dáme": 1.5,
        "doble": 0.8, "extra": 0.5, "al carrito": 2.5,
    },
    "informacion": {
        "información": 1.5, "informacion": 1.5,
        "ingrediente": 2.0, "ingredientes": 2.0, "contiene": 2.0,
        "qué lleva": 3.0, "que lleva": 3.0, "lleva": 1.5,
        "qué tiene": 2.5, "que tiene": 2.5, "de qué": 1.5, "de que": 1.5,
        "cómo es": 2.0, "como es": 2.0, "cuéntame": 1.5,
        "alérgeno": 2.5, "alergeno": 2.5, "gluten": 2.0,
        "calórias": 1.5, "calorias": 1.5, "nutri": 1.5,
    },
    "recomendacion": {
        "recomienda": 2.0, "recomiendas": 2.0, "sugieres": 2.0,
        "sugiere": 2.0, "qué me recomiendas": 3.0,
        "mejor": 1.0, "popular": 1.5, "favorito": 1.5,
        "especial": 0.8, "qué hay de": 1.5, "algo rico": 1.5,
    },
}


def _classify_intent(msg: str) -> str | None:
    """
    Clasifica la intención del mensaje por puntuación ponderada de palabras.

    Returns:
        'compra' | 'informacion' | 'recomendacion' | None
        None si ninguna intención supera el umbral mínimo.
    """
    msg_lower = msg.lower()
    scores: dict[str, float] = {}
    for intent, kw_weights in _INTENT_WEIGHTS.items():
        score = sum(w for kw, w in kw_weights.items() if kw in msg_lower)
        if score > 0:
            scores[intent] = score

    if not scores:
        return None
    best = max(scores, key=scores.__getitem__)
    return best if scores[best] >= 1.5 else None


# ===========================================================================
# NLU LOCAL — Capa 4: caché en memoria para respuestas de Gemini
# ===========================================================================

import hashlib as _hashlib
_gemini_cache: dict[str, dict] = {}
_CACHE_MAX: int = 60  # máximo de entradas en memoria (FIFO)


def _cache_key(message: str) -> str:
    return _hashlib.md5(message.strip().lower().encode()).hexdigest()


# ===========================================================================
# ██████  ██    ██ ██  ██████ ██   ██     ██████  ███████ ██████  ██    ██
# ██   ██ ██    ██ ██ ██      ██  ██      ██   ██ ██      ██   ██ ██    ██
# ██   ██ ██    ██ ██ ██      █████       ██████  █████   ██████  ██    ██
# ██   ██ ██    ██ ██ ██      ██  ██      ██   ██ ██      ██      ██    ██
# ██████   ██████  ██  ██████ ██   ██     ██   ██ ███████ ██       ██████
#
# LÓGICA DE DETECCIÓN — no necesitas editar esto normalmente
# ===========================================================================

def _get_quick_reply(message: str) -> dict | None:
    """
    Intercepta intenciones frecuentes con respuestas predefinidas.
    Evita una llamada a Gemini para preguntas simples.

    Seguridad crítica:
      - Pedidos: requiere current_user.is_authenticated.
      - Si el usuario menciona un número de pedido, consulta la BD
        filtrando SIEMPRE por user_id del usuario logueado.

    Returns:
        dict compatible con { reply, status, options? } o None si no hay match.
    """
    msg = message.lower().strip()

    # ── 1. Saludos ───────────────────────────────────────────────────
    if any(kw in msg for kw in _KEYWORDS["saludo"]):
        return {
            "reply": "¡Hola! Bienvenido a Duncan Dhu 🍔 ¿En qué te puedo ayudar hoy?",
            "status": "ok",
            "options": [
                {"text": "Ver Menú Rápido",        "next": "menu",              "style": "primary"},
                {"text": "Estado de mi Pedido",    "next": "order_status_hook", "style": "primary"},
                {"text": "Soporte / Ayuda",        "next": "help_order",        "style": "outline"},
            ],
        }

    # ── 2. Horarios ──────────────────────────────────────────────────
    if any(kw in msg for kw in _KEYWORDS["horarios"]):
        return {
            "reply": QUICK_REPLIES["horarios"],
            "status": "ok",
            "options": [
                {"text": "Ver Menú Rápido", "next": "menu",  "style": "primary"},
                {"text": "🔙 Volver al Inicio",  "next": "start", "style": "outline"},
            ],
        }

    # ── 3. Ubicación ──────────────────────────────────────────────────
    if any(kw in msg for kw in _KEYWORDS["ubicacion"]):
        return {
            "reply": QUICK_REPLIES["ubicacion"],
            "status": "ok",
            "options": [
                {"text": "🗺️ Google Maps", "action": "() => window.open('https://maps.google.com/?q=Calle+Principal+%23123,+Centro', '_blank')", "isLink": True, "style": "primary"},
                {"text": "🔙 Volver al Inicio", "next": "start", "style": "outline"},
            ],
        }

    # ── 4. Menú ───────────────────────────────────────────────────────────
    if any(kw in msg for kw in _KEYWORDS["menu"]):
        return {
            "reply": QUICK_REPLIES["menu"],
            "status": "ok",
            "options": [
                {
                    "text": "📖 Ver Menú Completo",
                    "action": "() => window.location.href = '/catalogo'",
                    "isLink": True,
                    "style": "primary",
                }
            ],
        }

    # ── 5. Precios ────────────────────────────────────────────────────────
    if any(kw in msg for kw in _KEYWORDS["precio"]):
        return {
            "reply": QUICK_REPLIES["precio"],
            "status": "ok",
            "options": [
                {
                    "text": "💰 Ver Precios en el Menú",
                    "action": "() => window.location.href = '/catalogo'",
                    "isLink": True,
                    "style": "primary",
                }
            ],
        }

    # ── 6. Métodos de pago ────────────────────────────────────────────────
    if any(kw in msg for kw in _KEYWORDS["pago"]):
        return {
            "reply": QUICK_REPLIES["pago"],
            "status": "ok",
            "options": [
                {"text": "🔙 Volver al Inicio", "next": "start", "style": "outline"},
            ],
        }

    # ── 7. Pedidos (SEGURIDAD CRÍTICA) ───────────────────────────────────
    # Detectamos intención de pedido: palabras clave OR número de orden
    order_num = _detect_order_number(msg)
    has_order_kw = any(kw in msg for kw in _KEYWORDS["pedido"])

    if has_order_kw or order_num:
        # 7a. Visitante no autenticado → bloquear, nunca mostrar datos
        if not current_user.is_authenticated:
            return {
                "reply": QUICK_REPLIES["pedido_guest"],
                "status": "ok",
                "options": [
                    {
                        "text": "🔑 Iniciar Sesión",
                        "action": "() => window.location.href = '/login'",
                        "isLink": True,
                        "style": "primary",
                    },
                    {
                        "text": "📝 Crear Cuenta",
                        "action": "() => window.location.href = '/registro'",
                        "isLink": True,
                        "style": "secondary",
                    },
                ],
            }

        # 7b. Usuario logueado + número de pedido → consultar BD segura
        if order_num:
            order = Order.query.filter_by(
                id=order_num,
                user_id=current_user.id,   # NUNCA omitir este filtro
            ).first()

            if not order:
                return {
                    "reply": QUICK_REPLIES["pedido_no_encontrado"],
                    "status": "ok",
                    "options": [
                        {
                            "text": "📦 Mis Pedidos",
                            "action": "() => window.location.href = '/mis-pedidos'",
                            "isLink": True,
                            "style": "primary",
                        }
                    ],
                }

            estado_emoji = {
                "pendiente":   "⏳",
                "preparando":  "👨‍🍳",
                "listo":       "✅",
                "entregado":   "🚀",
                "cancelado":   "❌",
            }.get(order.status, "📦")

            return {
                "reply": (
                    f"{estado_emoji} Tu pedido #{order.id} está en estado "
                    f"'{order.status.capitalize()}'. "
                    f"Total: ${float(order.total):.2f}. "
                    f"Método de pago: {order.payment_method}."
                ),
                "status": "ok",
                "options": [
                    {
                        "text": "📦 Ver Todos mis Pedidos",
                        "action": "() => window.location.href = '/mis-pedidos'",
                        "isLink": True,
                        "style": "primary",
                    }
                ],
            }

        # 7c. Solo palabras de pedido sin número → guiar al usuario
        return {
            "reply": (
                "📦 Para consultar el estado de tu pedido dime el número de orden "
                "o visita la sección 'Mis Pedidos'."
            ),
            "status": "ok",
            "options": [
                {
                    "text": "📦 Mis Pedidos",
                    "action": "() => window.location.href = '/mis-pedidos'",
                    "isLink": True,
                    "style": "primary",
                }
            ],
        }

    # Sin coincidencia → dejar pasar a Gemini
    return None


# ===========================================================================
# Interfaz pública
# ===========================================================================

def process_message(user_message: str, is_admin: bool = False) -> dict:
    """
    Orquesta el flujo completo de respuesta del chatbot:

      1. Quick Reply (solo flujo cliente) → respuesta inmediata sin Gemini.
      2. Gemini RAG → para preguntas más complejas o flujo admin.

    Args:
        user_message: Texto enviado desde el formulario libre del chatbot.
        is_admin:     Si True, salta quick replies y usa el prompt de admin.

    Returns:
        Dict con keys ``reply`` (str) y ``status`` (str).
        Compatible con el endpoint ``/api/chat``.
    """
    # ── Capa 1: Quick Reply (palabras clave exactas) ───────────────────────
    if not is_admin:
        quick = _get_quick_reply(user_message)
        if quick is not None:
            logger.info("ChatService [L1-QuickReply]: %r", user_message[:40])
            return quick

        # ── Capa 3 (ANTES que producto): Clasificador de intención ─────────────
        # Si la intención es 'informacion', saltar directo a Gemini;          
        # las preguntas de ingredientes nunca deben ir al Product NLU.         
        intent = _classify_intent(user_message)
        logger.info("ChatService [L3-Intent]: %r -> %s", user_message[:40], intent)

        if intent == "informacion":
            # Pasar directamente al bloque de Gemini (con caché)
            pass

        elif intent == "compra":
            # ── Capa 2: NLU — Detección de producto en BD ──────────────────
            product_reply = _detect_product_intent(user_message)
            if product_reply is not None:
                logger.info("ChatService [L2-ProductNLU]: %r", user_message[:40])
                return product_reply
            # Compra sin producto reconocido → guiar al menú
            return {
                "reply": (
                    "¿Qué se te antoja hoy? Haz clic en 'Ver Menú Rápido' "
                    "para ver nuestras opciones disponibles. 😋"
                ),
                "status": "ok",
                "options": [
                    {"text": "📖 Ver Menú Rápido", "next": "menu",  "style": "primary"},
                    {"text": "🛒 Ir al Catálogo",
                     "action": "() => window.location.href='/catalogo'",
                     "isLink": True, "style": "outline"},
                ],
            }

        else:
            # intent = 'recomendacion', None, o desconocido
            # Intentar product NLU de todos modos (puede haber nombre de producto)
            product_reply = _detect_product_intent(user_message)
            if product_reply is not None:
                logger.info("ChatService [L2-ProductNLU fallback]: %r", user_message[:40])
                return product_reply
            # Sin match de producto → continuar a Gemini con caché

        # ── Capa 4: Caché de Gemini ───────────────────────────────────────────
        cache_key = _cache_key(user_message)
        if cache_key in _gemini_cache:
            logger.info("ChatService [L4-Cache]: hit para %r", user_message[:40])
            return _gemini_cache[cache_key]

    # ── Fallback: sin API key configurada ─────────────────────────────────
    api_key: str = current_app.config.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.info("ChatService: GEMINI_API_KEY no configurada, usando modo fallback.")
        return {
            "reply": (
                "🔧 El asistente de IA no está configurado aún. "
                "Usa los botones del menú para navegar o contáctanos directamente."
            ),
            "status": "no_api_key",
        }

    # ── Import lazily para no romper la app si el paquete no está instalado ──
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        logger.error("ChatService: paquete 'google-generativeai' no instalado.")
        return {
            "reply": "🔧 Módulo de IA no disponible. Instala: pip install google-generativeai",
            "status": "import_error",
        }

    # ── RAG: Bifurcación de Personalidad (Admin vs Cliente) ────────────────
    if is_admin:
        try:
            from datetime import datetime
            hoy = datetime.now().date()

            pendientes = Order.query.filter_by(status='pendiente', archived=False).count()
            completados = Order.query.filter_by(status='completado').filter(
                func.date(Order.created_at) == hoy
            ).count()
            ingresos_query = db.session.query(func.sum(Order.total)).filter(
                Order.archived == False,
                Order.status != 'cancelado'
            ).scalar()
            ingresos = float(ingresos_query) if ingresos_query else 0.0

            admin_context = (
                f"- Pedidos Pendientes Activos: {pendientes}\\n"
                f"- Pedidos Completados Hoy: {completados}\\n"
                f"- Ingresos Totales (No archivado/cancelado): ${ingresos:.2f}\\n"
            )
        except Exception as e:
            logger.warning("ChatService (Admin): Error calculando métricas - %s", e)
            admin_context = "- Error obteniendo métricas en tiempo real.\\n"

        system_instruction = (
            "Eres DuncanBot Admin Protocol. Eres el asistente analítico y operativo "
            "de back-office para el restaurante Duncan Dhu. Tu personalidad es profesional, "
            "directa, analítica y extremadamente concisa.\\n\\n"
            "MÉTRICAS EN TIEMPO REAL DEL NEGOCIO:\\n"
            f"{admin_context}\\n\\n"
            "Responde a las dudas del administrador sobre el negocio basándote ÚNICAMENTE "
            "en estos datos. No inventes ventas ni pedidos. Si te preguntan por algo que "
            "no está en las métricas (facturación de ayer, stock, etc), responde que no "
            "tienes acceso a esa métrica en particular por ahora.\\n\\n"
            "REGLA CRÍTICA DE FORMATO: Está estrictamente prohibido usar Markdown. "
            "No uses asteriscos (*), ni negritas (**texto**), ni listas con guiones (-), "
            "ni saltos de línea (\\\\n). Debes responder siempre en un solo párrafo "
            "continuo de texto plano conversacional."
        )
    else:
        # RAG del Menú para Clientes (preguntas no capturadas por quick reply)
        menu_text = _build_menu_context()

        system_instruction = (
            "Eres DuncanBot, el asistente virtual del restaurante de hamburguesas "
            "Duncan Dhu. Tu personalidad es amable, directa y con un toque urbano. "
            "Responde siempre en español, de forma breve (máximo 3 oraciones). "
            "No uses listas largas; si hay muchos productos menciona solo los más destacados. "
            "Solo ofreces productos del menú actual. Si el usuario pregunta algo "
            "completamente ajeno al restaurante o la comida, redirige la conversación "
            "con amabilidad hacia las hamburguesas o el menú.\\n\\n"

            # ── CONOCIMIENTO COMPLETO DEL NEGOCIO ──
            "INFORMACIÓN DEL RESTAURANTE:\\n"
            "- Nombre: Duncan Dhu\\n"
            "- Tipo: Restaurante de hamburguesas artesanales\\n"
            "- Horario: Lunes a Domingo de 12:00 PM a 10:00 PM\\n"
            "- Dirección: Calle Principal #123, Centro\\n"
            "- Métodos de pago: Efectivo y tarjeta (Mercado Pago)\\n"
            "- Política de pedidos: Los pedidos se confirman en cuanto el staff "
            "  los acepta. El cliente recibe notificación por correo.\\n"
            "- Para cancelaciones: Contactar antes de que el pedido esté en preparación.\\n"
            "- Redes sociales: Instagram, Facebook, TikTok (@DuncanDhu).\\n\\n"

            "REGLA CRÍTICA DE FORMATO: Responde en texto plano conversacional continuo. "
            "Está estrictamente prohibido usar Markdown (sin asteriscos, sin negritas, sin listas). "
            "Completa siempre tus oraciones y tus ideas de forma natural, no dejes frases a medias. "
            "Sin viñetas, sin títulos, sin formato especial.\\n\\n"
            "REGLA CRÍTICA DE ACCIONES: No tienes capacidad de agregar productos al carrito, "
            "procesar pagos, confirmar pedidos ni realizar ninguna acción en el sistema. "
            "Si el usuario te pide que agregue algo, NUNCA digas que lo hiciste. "
            "En cambio, indícale que puede usar los botones del chat o ir al catálogo. "
            "Respuesta correcta: 'Para agregar ese producto, usa los botones de abajo o visita el catálogo.'\\n\\n"
            f"MENÚ ACTUAL DE DUNCAN DHU:\\n{menu_text}"
        )

    # ── Llamada a la API de Gemini ─────────────────────────────────────────
    try:
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_instruction,
        )

        response = model.generate_content(
            user_message,
            generation_config=genai.GenerationConfig(
                max_output_tokens=500,   # aumentado: evita cortar oraciones a la mitad
                temperature=0.7,
                top_p=0.9,
            ),
            safety_settings={
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            }
        )

        raw_text: str = response.text or ""

        clean_text = (
            raw_text
            .replace("**", "")
            .replace("*", "")
            .replace("- ", "")
            .replace("\n\n", " ")
            .replace("\n", " ")
            .replace("  ", " ")
            .strip()
        )
        clean_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', clean_text)

        if not clean_text:
            clean_text = "No pude generar una respuesta. Intenta reformular tu pregunta."

        result = {"reply": clean_text, "status": "ok"}

        # Guardar en caché solo si el mensaje es de cliente (no admin)
        if not is_admin:
            if len(_gemini_cache) >= _CACHE_MAX:
                _gemini_cache.pop(next(iter(_gemini_cache)))  # FIFO eviction
            _gemini_cache[_cache_key(user_message)] = result

        return result

    except Exception as exc:  # pylint: disable=broad-except
        error_msg_str = str(exc)
        print(f"\n🚨 [ChatService Error] Tipo: {type(exc).__name__} | Detalles: {error_msg_str}\n",
              flush=True)
        logger.error("ChatService: Error al llamar a Gemini API: %s", exc)

        # Rate Limit 429
        if "429" in error_msg_str or "quota" in error_msg_str.lower():
            return {
                "reply": "¡Uf! Estoy recibiendo muchos mensajes a la vez 😅. "
                         "Por favor, dame 1 minuto para tomar aire y vuelve a preguntarme.",
                "status": "rate_limit",
            }

        return {
            "reply": "Ups, tuve un pequeño mareo técnico. ¿Podemos intentar de nuevo en un momento?",
            "status": "api_error",
        }
