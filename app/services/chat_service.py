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

import hashlib as _hashlib
import logging
import re
import time
import unicodedata

from flask import current_app
from flask_login import current_user
from sqlalchemy import func

from app.extensions import db
from app.models import Category, Order, Product  # noqa: F401

logger = logging.getLogger(__name__)


# ===========================================================================
# MENSAJES PREDEFINIDOS — edita aquí sin tocar la lógica de detección
# ===========================================================================
QUICK_REPLIES: dict[str, str] = {
    "saludo": (
        "¡Hola! Bienvenido a Duncan Dhu 🍔 "
        "¿En qué te puedo ayudar hoy? Puedes preguntarme sobre nuestro menú, "
        "horarios, ubicación o el estado de tu pedido."
    ),
    "horarios": (
        "🕒 Nuestro horario de atención es de lunes a domingo, "
        "de 12:00 PM a 10:00 PM. ¡Te esperamos!"
    ),
    "ubicacion": (
        "📍 Nos encontramos en Calle Principal #123, Centro. "
        "¡Ven a visitarnos o haz tu pedido en línea!"
    ),
    "menu": (
        "🍔 Tenemos hamburguesas, snacks y bebidas que te van a encantar. "
        "Puedes ver nuestro menú completo haciendo clic en el botón de abajo."
    ),
    "precio": (
        "💰 Nuestros precios varían según el producto. "
        "Te invito a revisar el menú completo para ver todos los precios. "
        "¡Tenemos opciones para todos los presupuestos!"
    ),
    "pago": (
        "💳 Aceptamos pago en efectivo y con tarjeta a través de Mercado Pago. "
        "Elige el que más te convenga al momento de hacer tu pedido."
    ),
    "pedido_guest": (
        "🔐 Para consultar el estado de tu pedido necesito verificar tu identidad. "
        "Por favor, inicia sesión y podrás ver todos tus pedidos desde 'Mis Pedidos'."
    ),
    "pedido_no_encontrado": (
        "🔍 No encontré un pedido con ese número en tu cuenta. "
        "Revisa el número de pedido en tu confirmación o ve a 'Mis Pedidos'."
    ),
    "despedida": (
        "¡Hasta pronto! Recuerda que aquí estamos para calmar tus antojos. 🍔👋 "
        "¡Que tengas un excelente día!"
    ),
    "agradecimiento": (
        "¡Con mucho gusto! Para eso estamos. 😎 ¿Hay algo más en lo que te pueda ayudar hoy?"
    ),
    "recomendacion": (
        "¡Uf! Si es tu primera vez, te recomiendo nuestra Hamburguesa Clásica o un buen Combo. 🤤 "
        "Haz clic abajo para ver nuestras opciones más populares."
    ),
    # 🚨 NUEVO: Respuesta para envíos a domicilio
    "envios": (
        "🛵 Por el momento no contamos con servicio a domicilio. "
        "Todas nuestras órdenes son para recoger directamente en sucursal "
        "(Calle Principal #123). ¡Puedes hacer tu pedido en línea aquí mismo para que esté listo cuando llegues!"
    ),
}

# Palabras clave por intención (listas editables)
_KEYWORDS: dict[str, list[str]] = {
    "saludo": [
        "hola",
        "holaa",
        "holaaa",
        "buenas",
        "saludos",
        "hey",
        "hi",
        "buen día",
        "buenos días",
        "buenas tardes",
        "buenas noches",
        "qué tal",
        "que tal",
        "holi",
    ],
    "despedida": [
        "adiós",
        "adios",
        "bye",
        "hasta luego",
        "nos vemos",
        "chao",
        "hasta pronto",
    ],
    "agradecimiento": [
        "gracias",
        "muchas gracias",
        "te lo agradezco",
        "mil gracias",
        "ok",
        "perfecto",
        "excelente",
        "vale",
        "genial",
    ],
    "recomendacion": [
        "recomendacion",
        "recomendaciones",
        "recomienda",
        "recomiendas",
        "sugieres",
        "sugerencia",
        "popular",
        "favorito",
        "antojo",
        "mejores",
        "mejor",
    ],
    # 🚨 NUEVO: Categoría para envíos y domicilios
    "envios": [
        "envio",
        "envío",
        "envios",
        "envíos",
        "domicilio",
        "delivery",
        "repartidor",
        "reparto",
        "llevan",
        "mandan",
        "entregas",
        "entregan",
    ],
    "horarios": [
        "horario",
        "horarios",
        "hora",
        "horas",
        "abre",
        "cierra",
        "abierto",
        "open",
        "cuando abren",
        "a qué hora",
        "turno",
    ],
    "ubicacion": [
        "ubicación",
        "ubi",
        "ubicacion",
        "dirección",
        "direccion",
        "donde",
        "están",
        "estan",
        "encuentran",
        "lugar",
        "domicilio",
        "calle",
        "mapa",
        "maps",
    ],
    "menu": [
        "menú",
        "menuu",
        "menu",
        "carta",
        "platillo",
        "platillos",
        "opciones",
        "que tienen",
        "comida",
        "hamburguesas",
        "hamburguesa",
        "catálogo",
        "catalogo",
        "qué venden",
        "que venden",
        "productos",
        "novedades",
        "antojos",
    ],
    "hotdog": [
        "hot dogs",
        "hotdog",
        "hotdogs",
        "jocho",
        "jochos",
        "perros calientes",
        "perro caliente",
    ],
    "bebida": [
        "bebidas",
        "bebida",
        "refresco",
        "refrescos",
        "soda",
        "agua",
        "aguas",
        "tomar",
        "pa tomar",
        "para tomar",
        "jugo",
        "malteada",
        "malteadas",
    ],
    "postre": [
        "postres",
        "postre",
        "dulce",
        "dulces",
        "helado",
        "helados",
        "pastel",
        "pay",
    ],
    "snack": [
        "snacks",
        "snack",
        "papas",
        "papitas",
        "papas a la francesa",
        "boneless",
        "alitas",
        "aros de cebolla",
    ],
    "combo": [
        "combos",
        "combo",
        "paquete",
        "paquetes",
        "promo",
        "promocion",
        "promoción",
        "promociones",
    ],
    "precio": [
        "precio",
        "precios",
        "cuánto",
        "cuanto",
        "cuesta",
        "cuestan",
        "costo",
        "cobran",
        "valen",
    ],
    "pago": [
        "metodo",
        "metodos",
        "metodos de pago",
        "forma de pago",
        "pago",
        "pagos",
        "pagar",
        "efectivo",
        "tarjeta",
        "mercado pago",
        "mercadopago",
        "transferencia",
        "como pago",
        "cómo pago",
    ],
    "pedido": [
        "pedido",
        "orden",
        "order",
        "pedí",
        "pedi",
        "compré",
        "compre",
        "estado de mi pedido",
        "mi orden",
        "dónde está",
        "donde esta",
        "llegó",
        "llego",
    ],
    "contacto": [
        "contacto",
        "contactar",
        "contáctanos",
        "contactanos",
        "queja",
        "quejas",
        "reclamacion",
        "reclamación",
        "reclamo",
        "sugerencia",
        "sugerencias",
        "reembolso",
        "reembolsos",
        "devolucion",
        "devolución",
        "devolver",
        "problemas",
        "asesor",
        "asesores",
    ],
    "cuenta": [
        "perfil",
        "correo",
        "contraseña",
        "contrasena",
        "recuperar cuenta",
        "login",
        "iniciar sesion",
        "iniciar sesión",
        "mi cuenta",
    ],
    "ayuda": [
        "informacion",
        "información",
        "info",
        "ayuda",
        "help",
        "soporte",
        "apoyo",
        "orientacion",
        "orientación",
    ],
}


# ===========================================================================
# Helpers internos
# ===========================================================================


def _build_menu_context() -> str:
    try:
        products = (
            Product.query.filter_by(active=True)
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
    except Exception as exc:
        logger.warning("ChatService: no se pudo leer el menú de la BD: %s", exc)
        return "(Menú temporalmente no disponible)"


def _sanitize_markdown(text: str) -> str:
    text = re.sub(r"\*(?!\*)(.*?)\*(?!\*)", r"\1", text)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _detect_order_number(text: str) -> int | None:
    match = re.search(r"\b(\d{1,6})\b", text)
    return int(match.group(1)) if match else None


# ===========================================================================
# NLU LOCAL — Capa 2: detección de producto desde BD
# ===========================================================================

_MODIFICATION_WORDS: list[str] = [
    "sin",
    "extra",
    "con extra",
    "doble",
    "más",
    "mas",
    "menos",
    "aparte",
    "al lado",
    "sin cebolla",
    "sin chile",
    "bien cocido",
    "término",
    "termino",
]

_STOP_WORDS: frozenset[str] = frozenset(
    {"de", "la", "el", "los", "las", "del", "un", "una", "y", "o", "con", "sin"}
)


def _normalize(s: str) -> str:
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


def _significant_words(name: str) -> list[str]:
    return [w for w in _normalize(name).split() if w not in _STOP_WORDS and len(w) > 2]


_products_cache: list = []
_products_cache_ts: float = 0.0
_PRODUCTS_TTL: float = 300.0


def _get_active_products() -> list:
    global _products_cache, _products_cache_ts
    if time.monotonic() - _products_cache_ts > _PRODUCTS_TTL:
        try:
            _products_cache = Product.query.filter_by(active=True).all()
            _products_cache_ts = time.monotonic()
        except Exception as exc:
            logger.warning("ProductCache: fallo al recargar: %s", exc)
    return _products_cache


def _detect_product_intent(msg: str) -> dict | None:
    msg_normalized = _normalize(msg)
    products = _get_active_products()
    if not products:
        return None

    products_sorted = sorted(products, key=lambda p: len(p.name), reverse=True)
    msg_words = set(msg_normalized.split())
    matched: list[Product] = []

    for p in products_sorted:
        sig_words = _significant_words(p.name)
        if not sig_words:
            continue
        if _normalize(p.name) in msg_normalized:
            matched.append(p)
            continue
        hits = sum(1 for w in sig_words if w in msg_words)
        threshold = (
            len(sig_words) if len(sig_words) <= 2 else max(2, len(sig_words) - 1)
        )
        if hits >= threshold:
            matched.append(p)

    if not matched:
        return None

    has_modification = any(w in msg.lower() for w in _MODIFICATION_WORDS)
    options = [
        {
            "text": f"➕ Agregar {p.name} (${float(p.price):.2f})",
            "mutationHookUrl": f"/carrito/agregar/{p.id}",
            "requiresAuth": True,
            "style": "primary",
        }
        for p in matched
    ]
    options.append(
        {"text": "📖 Ver todas las opciones", "next": "menu", "style": "outline"}
    )

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

    return {"reply": reply, "status": "ok", "options": options}


# ===========================================================================
# NLU LOCAL — Capa 3: clasificador de intención por puntuación
# ===========================================================================

_INTENT_WEIGHTS: dict[str, dict[str, float]] = {
    "compra": {
        "quiero": 1.5,
        "dame": 1.5,
        "pide": 1.2,
        "pedir": 1.2,
        "me das": 2.0,
        "agrega": 2.0,
        "agrego": 1.5,
        "añade": 2.0,
        "añadir": 2.0,
        "añademe": 2.0,
        "ordena": 1.5,
        "quiero pedir": 2.5,
        "ponme": 1.5,
        "trae": 1.5,
        "doble": 0.8,
        "extra": 0.5,
        "al carrito": 2.5,
    },
}

_INTENT_PATTERNS: dict[str, list[tuple[re.Pattern, float]]] = {
    intent: [
        (re.compile(r"\b" + re.escape(_normalize(kw)) + r"\b"), weight)
        for kw, weight in kw_weights.items()
    ]
    for intent, kw_weights in _INTENT_WEIGHTS.items()
}


def _classify_intent(msg: str) -> str | None:
    msg_norm = _normalize(msg)
    scores: dict[str, float] = {}
    for intent, patterns in _INTENT_PATTERNS.items():
        score = sum(weight for pattern, weight in patterns if pattern.search(msg_norm))
        if score > 0:
            scores[intent] = score

    if not scores:
        return None
    best = max(scores, key=scores.__getitem__)
    return best if scores[best] >= 1.5 else None


# ===========================================================================
# NLU LOCAL — Capa 4: caché en memoria para respuestas de Gemini
# ===========================================================================

_gemini_cache: dict[str, dict] = {}
_CACHE_MAX: int = 60


def _cache_key(message: str, is_admin: bool = False) -> str:
    role = "admin" if is_admin else "user"
    return _hashlib.md5(f"{role}:{message.strip().lower()}".encode()).hexdigest()


# ===========================================================================
# LÓGICA DE DETECCIÓN
# ===========================================================================


def _aggressive_keyword_match(message: str, keywords: list[str]) -> bool:
    msg_norm = _normalize(message)
    for keyword in keywords:
        kw_norm = _normalize(keyword)
        pattern = re.compile(r"\b" + re.escape(kw_norm) + r"\b", re.IGNORECASE)
        if pattern.search(msg_norm):
            return True
    return False


def _get_admin_quick_reply(message: str) -> dict | None:
    msg = message.lower().strip()

    # ── 1. SALUDOS ADMIN ───────────────────────────────────────────
    if _aggressive_keyword_match(msg, _KEYWORDS["saludo"]):
        try:
            pendientes = Order.query.filter_by(
                status="pendiente", archived=False
            ).count()
            completados = Order.query.filter_by(status="completado").count()
            ingresos_query = (
                db.session.query(func.sum(Order.total))
                .filter(Order.archived == False, Order.status != "cancelado")
                .scalar()
            )
            ingresos = float(ingresos_query) if ingresos_query else 0.0

            reply = (
                f"Hola Admin 👋 Panel actual: {pendientes} pedidos pendientes, "
                f"{completados} completados hoy, ${ingresos:.2f} de ingresos. "
                f"¿En qué puedo ayudarte?"
            )
        except Exception as e:
            logger.warning("AdminFSM: Error calculando métricas en saludo: %s", e)
            reply = "Hola Admin 👋 Bienvenido al panel. ¿En qué puedo ayudarte?"

        return {
            "reply": reply,
            "status": "ok",
            "options": [
                {
                    "text": "📊 Ver Dashboard",
                    "action": "() => window.location.href='/admin'",
                    "isLink": True,
                    "style": "primary",
                },
                {
                    "text": "📦 Órdenes Pendientes",
                    "action": "() => window.location.href='/admin/ordenes'",
                    "isLink": True,
                    "style": "primary",
                },
                {
                    "text": "📈 Reportes",
                    "action": "() => window.location.href='/admin/reportes'",
                    "isLink": True,
                    "style": "outline",
                },
            ],
        }

    # ── 2. INFORMACIÓN DE PEDIDOS (Admin) ──────────────────────────
    if _aggressive_keyword_match(msg, _KEYWORDS["pedido"]):
        pendientes = Order.query.filter_by(status="pendiente", archived=False).count()
        return {
            "reply": f"Tienes {pendientes} pedidos en estado 'pendiente' esperando procesamiento.",
            "status": "ok",
            "options": [
                {
                    "text": "📦 Ir a Órdenes",
                    "action": "() => window.location.href='/admin/ordenes'",
                    "isLink": True,
                    "style": "primary",
                }
            ],
        }

    # ── 3. HORARIOS (Admin) ────────────────────────────────────────
    if _aggressive_keyword_match(msg, _KEYWORDS["horarios"]):
        return {
            "reply": "🕒 Duncan Dhu abre de Lunes a Domingo, 12:00 PM – 10:00 PM.",
            "status": "ok",
        }

    # ── 4. AYUDA (Admin) ───────────────────────────────────────────
    if _aggressive_keyword_match(msg, _KEYWORDS["ayuda"]):
        return {
            "reply": "¿Necesitas ayuda? Puedo asistirte navegando a los paneles principales.",
            "status": "ok",
            "options": [
                {
                    "text": "📦 Órdenes",
                    "action": "() => window.location.href='/admin/ordenes'",
                    "isLink": True,
                    "style": "primary",
                },
                {
                    "text": "📊 Dashboard",
                    "action": "() => window.location.href='/admin'",
                    "isLink": True,
                    "style": "primary",
                },
            ],
        }

    return None


def _get_quick_reply(message: str) -> dict | None:
    msg = message.lower().strip()

    # ── 1. SALUDOS, DESPEDIDAS, AGRADECIMIENTOS, RECOMENDACIONES, Y ENVÍOS ───

    if _aggressive_keyword_match(msg, _KEYWORDS["saludo"]):
        return {
            "reply": "¡Hola! Bienvenido a Duncan Dhu 🍔 ¿En qué te puedo ayudar hoy?",
            "status": "ok",
            "options": [
                {"text": "Ver Menú Rápido", "next": "menu", "style": "primary"},
                {
                    "text": "Estado de mi Pedido",
                    "next": "order_status_hook",
                    "style": "primary",
                },
                {"text": "Soporte / Ayuda", "next": "help_order", "style": "outline"},
            ],
        }

    if _aggressive_keyword_match(msg, _KEYWORDS["despedida"]):
        return {
            "reply": QUICK_REPLIES["despedida"],
            "status": "ok",
            "options": [
                {"text": "📖 Ver Menú Rápido", "next": "menu", "style": "primary"},
            ],
        }

    if _aggressive_keyword_match(msg, _KEYWORDS["agradecimiento"]):
        return {
            "reply": QUICK_REPLIES["agradecimiento"],
            "status": "ok",
            "options": [
                {"text": "📖 Ver Menú", "next": "menu", "style": "primary"},
                {
                    "text": "📦 Estado de mi Pedido",
                    "next": "order_status_hook",
                    "style": "outline",
                },
            ],
        }

    if _aggressive_keyword_match(msg, _KEYWORDS["recomendacion"]):
        return {
            "reply": QUICK_REPLIES["recomendacion"],
            "status": "ok",
            "options": [
                {
                    "text": "🍔 Ver Combos",
                    "action": "() => window.location.href = '/catalogo#category-combos'",
                    "isLink": True,
                    "style": "primary",
                },
                {
                    "text": "📖 Ver Catálogo Completo",
                    "action": "() => window.location.href = '/catalogo'",
                    "isLink": True,
                    "style": "outline",
                },
            ],
        }

    # 🚨 NUEVO INTERCEPTOR: Envíos a Domicilio
    if _aggressive_keyword_match(msg, _KEYWORDS["envios"]):
        return {
            "reply": QUICK_REPLIES["envios"],
            "status": "ok",
            "options": [
                {
                    "text": "📍 Ver Ubicación",
                    "action": "() => window.open('https://maps.google.com/?q=Calle+Principal+%23123,+Centro', '_blank')",
                    "isLink": True,
                    "style": "primary",
                },
                {"text": "📖 Ver Menú", "next": "menu", "style": "outline"},
            ],
        }

    # ── 2. PREGUNTAS GENERALES ──────────────────────────────────────────────

    if _aggressive_keyword_match(msg, _KEYWORDS["horarios"]):
        return {
            "reply": QUICK_REPLIES["horarios"],
            "status": "ok",
            "options": [
                {"text": "Ver Menú Rápido", "next": "menu", "style": "primary"},
                {"text": "🔙 Volver al Inicio", "next": "start", "style": "outline"},
            ],
        }

    if _aggressive_keyword_match(msg, _KEYWORDS["ubicacion"]):
        return {
            "reply": QUICK_REPLIES["ubicacion"],
            "status": "ok",
            "options": [
                {
                    "text": "🗺️ Google Maps",
                    "action": "() => window.open('https://maps.google.com/?q=Calle+Principal+%23123,+Centro', '_blank')",
                    "isLink": True,
                    "style": "primary",
                },
                {"text": "🔙 Volver al Inicio", "next": "start", "style": "outline"},
            ],
        }

    if _aggressive_keyword_match(msg, _KEYWORDS["menu"]):
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

    if _aggressive_keyword_match(msg, _KEYWORDS["precio"]):
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

    if _aggressive_keyword_match(msg, _KEYWORDS["pago"]):
        return {
            "reply": QUICK_REPLIES["pago"],
            "status": "ok",
            "options": [
                {"text": "🔙 Volver al Inicio", "next": "start", "style": "outline"},
            ],
        }

    # ── 3. ESTADO DE PEDIDOS Y AYUDA ─────────────────────────────────────────

    order_num = _detect_order_number(msg)
    has_order_kw = any(kw in msg for kw in _KEYWORDS["pedido"])

    if has_order_kw or order_num:
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

        if order_num:
            order = Order.query.filter_by(
                id=order_num,
                user_id=current_user.id,
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
                "pendiente": "⏳",
                "preparando": "👨‍🍳",
                "listo": "✅",
                "entregado": "🚀",
                "cancelado": "❌",
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

    if any(kw in msg for kw in _KEYWORDS["ayuda"]):
        return {
            "reply": "¡Claro! ¿Sobre qué tema necesitas información? Puedo ayudarte con:",
            "status": "ok",
            "options": [
                {"text": "🍔 Ver el Menú", "next": "menu", "style": "primary"},
                {"text": "🕑 Horarios", "next": "info_general", "style": "outline"},
                {"text": "📍 Ubicación", "next": "info_general", "style": "outline"},
                {"text": "💳 Métodos de Pago", "next": "start", "style": "outline"},
                {
                    "text": "📦 Estado de mi Pedido",
                    "next": "order_status_hook",
                    "style": "outline",
                },
            ],
        }

    if any(kw in msg for kw in _KEYWORDS["contacto"]):
        return {
            "reply": (
                "¿Necesitas contactarnos? Puedes escribirnos directamente a nuestro correo "
                "oficial dunc.dhuisc@gmail.com o enviarnos un mensaje."
            ),
            "status": "ok",
            "options": [
                {
                    "text": "📨 Abrir Formulario de Contacto",
                    "action": "() => window.location.href = '/contactanos'",
                    "isLink": True,
                    "style": "primary",
                },
                {"text": "🔙 Volver al Inicio", "next": "start", "style": "outline"},
            ],
        }

    if any(kw in msg for kw in _KEYWORDS["cuenta"]):
        return {
            "reply": "Para gestionar tu cuenta, perfil, o contraseñas, por favor visita tu Perfil. 👤",
            "status": "ok",
            "options": [
                {
                    "text": "👤 Ir a Mi Perfil",
                    "action": "() => window.location.href = '/perfil'",
                    "isLink": True,
                    "style": "primary",
                },
                {
                    "text": "🔑 Iniciar Sesión",
                    "action": "() => window.location.href = '/login'",
                    "isLink": True,
                    "style": "outline",
                },
            ],
        }

    if any(kw in msg for kw in _KEYWORDS["hotdog"]):
        return {
            "reply": "¡Claro! Además de nuestras hamburguesas, preparamos deliciosos Hot Dogs. 🌭",
            "status": "ok",
            "options": [
                {
                    "text": "🌭 Ver Hot Dogs en el Menú",
                    "action": "() => window.location.href = '/catalogo#category-hot-dogs'",
                    "isLink": True,
                    "style": "primary",
                },
                {
                    "text": "📖 Volver al Menú Principal",
                    "next": "menu",
                    "style": "outline",
                },
            ],
        }

    if any(kw in msg for kw in _KEYWORDS["bebida"]):
        return {
            "reply": "Para acompañar tu comida, tenemos gran variedad de bebidas bien frías. 🥤",
            "status": "ok",
            "options": [
                {
                    "text": "🥤 Ver Bebidas en el Menú",
                    "action": "() => window.location.href = '/catalogo#category-bebidas'",
                    "isLink": True,
                    "style": "primary",
                },
                {
                    "text": "📖 Volver al Menú Principal",
                    "next": "menu",
                    "style": "outline",
                },
            ],
        }

    if any(kw in msg for kw in _KEYWORDS["postre"]):
        return {
            "reply": "¡Siempre hay espacio para el postre! Mira nuestras opciones dulces: 🍰",
            "status": "ok",
            "options": [
                {
                    "text": "🍰 Ver Postres en el Menú",
                    "action": "() => window.location.href = '/catalogo#category-postres'",
                    "isLink": True,
                    "style": "primary",
                },
                {
                    "text": "📖 Volver al Menú Principal",
                    "next": "menu",
                    "style": "outline",
                },
            ],
        }

    if any(kw in msg for kw in _KEYWORDS["snack"]):
        return {
            "reply": "Tenemos los mejores snacks para botanear o acompañar tu comida. 🍟",
            "status": "ok",
            "options": [
                {
                    "text": "🍟 Ver Snacks en el Menú",
                    "action": "() => window.location.href = '/catalogo#category-snacks'",
                    "isLink": True,
                    "style": "primary",
                },
                {
                    "text": "📖 Volver al Menú Principal",
                    "next": "menu",
                    "style": "outline",
                },
            ],
        }

    if any(kw in msg for kw in _KEYWORDS["combo"]):
        return {
            "reply": "¡Tenemos excelentes paquetes para calmar cualquier hambre! 🍔🍟🥤",
            "status": "ok",
            "options": [
                {
                    "text": "🍔 Ver Combos en el Menú",
                    "action": "() => window.location.href = '/catalogo#category-combos'",
                    "isLink": True,
                    "style": "primary",
                },
                {
                    "text": "📖 Volver al Menú Principal",
                    "next": "menu",
                    "style": "outline",
                },
            ],
        }

    return None


# ===========================================================================
# Interfaz pública
# ===========================================================================


def process_message(user_message: str, is_admin: bool = False) -> dict:
    # 🚨 FIX ARQUITECTÓNICO DEFINITIVO: Autodetección inquebrantable de Rol
    # Verificamos directamente con la sesión activa, ignorando el parámetro de la ruta
    is_admin_real = current_user.is_authenticated and getattr(
        current_user, "is_admin", False
    )

    user_message = user_message.strip()
    msg_lower = user_message.lower()

    # 1. Manejo de mensaje vacío (Carga inicial del chat)
    if not user_message:
        if is_admin_real:
            return _get_admin_quick_reply("hola") or {}
        else:
            return {
                "reply": "¿En qué te puedo ayudar?",
                "status": "ok",
                "options": [
                    {"text": "😄 Ver Menú", "next": "menu", "style": "primary"},
                    {"text": "⏰ Horarios", "next": "info_general", "style": "outline"},
                ],
            }

    # 2. CAPA 1: FSM AGGRESSIVE (Prioridad absoluta sin tocar IA)
    if is_admin_real:
        admin_reply = _get_admin_quick_reply(user_message)
        if admin_reply is not None:
            logger.info("ChatService [Admin-FSM]: %r", user_message[:40])
            return admin_reply

    if not is_admin_real:
        client_quick = _get_quick_reply(user_message)
        if client_quick is not None:
            logger.info("ChatService [Client-FSM]: %r", user_message[:40])
            return client_quick

    # 3. CAPA 2: NLU DE PRODUCTOS (Solo para clientes)
    if not is_admin_real:
        if re.search(r"\b(sin)\b", msg_lower):
            prod_match = _detect_product_intent(user_message)
            if prod_match is not None:
                return prod_match

            return {
                "reply": (
                    "🔍 He notado que tienes especificaciones para tu pedido.\n\n"
                    "Recuerda que el chat no puede aplicar modificaciones a los productos "
                    "por este medio. Se agregarán siempre con su receta original.\n\n"
                    "Para agregarlos, por favor dirígete a nuestro catálogo:"
                ),
                "status": "ok",
                "options": [
                    {
                        "text": "📖 Abrir el Catálogo Completo",
                        "action": "() => window.location.href='/catalogo'",
                        "isLink": True,
                        "style": "primary",
                    },
                    {"text": "🔙 Menú Principal", "next": "menu", "style": "outline"},
                ],
            }

        intent = _classify_intent(user_message)
        if intent == "compra":
            product_reply = _detect_product_intent(user_message)
            if product_reply is not None:
                return product_reply
            return {
                "reply": (
                    "¿Qué se te antoja hoy? Haz clic en 'Ver Menú Rápido' "
                    "para ver nuestras opciones disponibles. 😋"
                ),
                "status": "ok",
                "options": [
                    {"text": "📖 Ver Menú Rápido", "next": "menu", "style": "primary"},
                    {
                        "text": "🛒 Ir al Catálogo",
                        "action": "() => window.location.href='/catalogo'",
                        "isLink": True,
                        "style": "outline",
                    },
                ],
            }
        else:
            product_reply = _detect_product_intent(user_message)
            if product_reply is not None:
                return product_reply

        cache_key = _cache_key(user_message, is_admin=False)
        if cache_key in _gemini_cache:
            return _gemini_cache[cache_key]

    # 4. PREPARACIÓN DE IA (Fallback)
    api_key: str = current_app.config.get("GEMINI_API_KEY", "")
    if not api_key:
        return {
            "reply": "🔧 El asistente de IA no está configurado aún. Usa los botones del menú.",
            "status": "no_api_key",
        }

    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        return {
            "reply": "🔧 Módulo de IA no disponible.",
            "status": "import_error",
        }

    # 5. CONFIGURACIÓN DEL PROMPT POR ROL
    if is_admin_real:
        try:
            from datetime import datetime

            hoy = datetime.now().date()

            pendientes = Order.query.filter_by(
                status="pendiente", archived=False
            ).count()
            completados = (
                Order.query.filter_by(status="completado")
                .filter(func.date(Order.created_at) == hoy)
                .count()
            )
            ingresos_query = (
                db.session.query(func.sum(Order.total))
                .filter(Order.archived == False, Order.status != "cancelado")
                .scalar()
            )
            ingresos = float(ingresos_query) if ingresos_query else 0.0

            admin_context = (
                f"- Pedidos Pendientes Activos: {pendientes}\n"
                f"- Pedidos Completados Hoy: {completados}\n"
                f"- Ingresos Totales: ${ingresos:.2f}\n"
            )
        except Exception:
            admin_context = "- Error obteniendo métricas en tiempo real.\n"

        system_instruction = (
            "Eres DuncanBot Admin Protocol. Eres el asistente analítico de back-office. "
            "MÉTRICAS EN TIEMPO REAL:\n"
            f"{admin_context}\n\n"
            "Responde basándote ÚNICAMENTE en estos datos. No uses Markdown."
        )
    else:
        menu_text = _build_menu_context()
        system_instruction = (
            "IDENTIDAD: Eres DuncanBot, asistente del restaurante Duncan Dhu. Responde en español. "
            "LÍMITES DUROS: No ejecutas acciones. Si piden agregar algo, di: 'Usa los botones de abajo'. "
            f"MENÚ ACTUAL:\n{menu_text}"
        )

    # 6. LLAMADA A GEMINI
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_instruction,
        )

        response = model.generate_content(
            user_message,
            generation_config=genai.GenerationConfig(
                max_output_tokens=500,
                temperature=0.7,
                top_p=0.9,
            ),
            safety_settings={
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            },
            request_options={"timeout": 12},
        )

        raw_text: str = response.text or ""
        clean_text = (
            raw_text.replace("**", "")
            .replace("*", "")
            .replace("- ", "")
            .replace("\n\n", " ")
            .replace("\n", " ")
            .strip()
        )

        if not clean_text:
            clean_text = (
                "No pude generar una respuesta. Intenta reformular tu pregunta."
            )

        result = {"reply": clean_text, "status": "ok"}

        if not is_admin_real:
            if len(_gemini_cache) >= _CACHE_MAX:
                _gemini_cache.pop(next(iter(_gemini_cache)))
            _gemini_cache[_cache_key(user_message, is_admin=False)] = result

        return result

    except Exception as exc:
        error_msg_str = str(exc)
        logger.error("ChatService: Error al llamar a Gemini API: %s", exc)

        if "429" in error_msg_str or "quota" in error_msg_str.lower():
            return {
                "reply": "🛠️ El asistente alcanzó el límite de consultas por ahora. Usa los botones de navegación.",
                "status": "rate_limit",
                "options": [
                    {"text": "📖 Ver Menú", "next": "menu", "style": "primary"},
                    {
                        "text": "📧 Contáctanos",
                        "action": "() => window.location.href='/contactanos'",
                        "isLink": True,
                        "style": "outline",
                    },
                ],
            }

        return {
            "reply": "Ups, tuve un pequeño problema con tu consulta. ¿Podemos intentar de nuevo en un momento?",
            "status": "api_error",
        }
