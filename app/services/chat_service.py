"""Servicio de chat — DuncanBot con Google Gemini y patrón RAG básico.

Arquitectura:
  - Consulta la BD para obtener el menú activo (Product.active == True).
  - Construye un system_instruction con el menú real como contexto (RAG).
  - Llama al modelo gemini-1.5-flash con el mensaje del usuario.
  - Devuelve { "reply": "...", "status": "ok" } compatible con el FSM.

Fallback graceful:
  - Si GEMINI_API_KEY no está configurada → respuesta de mantenimiento.
  - Si la API falla → captura la excepción y devuelve mensaje de error amigable.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import func

from flask import current_app

from app.models import Product, Category, Order  # noqa: F401
from app.extensions import db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

        # Agrupar por categoría para mejor legibilidad en el prompt
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
    """Convierte Markdown básico de Gemini a texto plano / HTML seguro.

    Gemini puede devolver **negritas**, *itálicas* y listas con * ó -.
    El chatbot frontend ya interpreta **texto** → <strong>, así que
    mantenemos ese patrón y eliminamos el resto.
    """
    # Conservar **negritas** (el frontend las renderiza como <strong>)
    # Eliminar *itálicas* simples (deja el texto, quita los asteriscos)
    text = re.sub(r"\*(?!\*)(.*?)\*(?!\*)", r"\1", text)
    # Convertir listas con guión o asterisco a líneas con bullet unicode
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)
    # Normalizar múltiples líneas en blanco
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Interfaz pública
# ---------------------------------------------------------------------------

def process_message(user_message: str, is_admin: bool = False) -> dict:
    """Procesa un mensaje de texto libre del usuario con Gemini.

    Args:
        user_message: Texto enviado desde el formulario libre del chatbot.
        is_admin:     Reservado para personalización futura del prompt admin.

    Returns:
        Dict con keys ``reply`` (str) y ``status`` (str).
        Compatible con la respuesta esperada por el endpoint ``/api/chat``.
    """
    api_key: str = current_app.config.get("GEMINI_API_KEY", "")

    # ── Fallback: sin API key configurada ─────────────────────────────────
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
        # 1. Extraer métricas básicas del negocio
        try:
            from datetime import datetime
            hoy = datetime.now().date()
            
            # Pedidos pendientes
            pendientes = Order.query.filter_by(status='pendiente', archived=False).count()
            
            # Pedidos completados hoy (filtrado simplificado en memoria o BD)
            completados = Order.query.filter_by(status='completado').filter(
                func.date(Order.created_at) == hoy
            ).count()
            
            # Total de ingresos (solo ordenes no archivadas y sumando su total)
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
        # Flujo origina: RAG del Menú para Clientes
        menu_text = _build_menu_context()

        system_instruction = (
            "Eres DuncanBot, el asistente virtual del restaurante de hamburguesas "
            "Duncan Dhu. Tu personalidad es amable, directa y con un toque urbano. "
            "Responde siempre en español, de forma breve (máximo 3 oraciones). "
            "No uses listas largas; si hay muchos productos menciona solo los más destacados. "
            "Solo ofreces productos del menú actual. Si el usuario pregunta algo "
            "completamente ajeno al restaurante o la comida, redirige la conversación "
            "con amabilidad hacia las hamburguesas o el menú.\\n\\n"
            "REGLA CRÍTICA DE FORMATO: Está estrictamente prohibido usar Markdown. "
            "No uses asteriscos (*), ni negritas (**texto**), ni listas con guiones (-), "
            "ni saltos de línea (\\\\n). Debes responder siempre en un solo párrafo "
            "continuo de texto plano conversacional. Sin viñetas, sin títulos, sin formato especial.\\n\\n"
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
                max_output_tokens=256,   # respuestas cortas para un chat
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

        # Sanitización de seguridad: elimina cualquier Markdown residual que
        # el modelo haya filtrado a pesar de la instrucción del prompt.
        clean_text = (
            raw_text
            .replace("**", "")      # negritas Markdown
            .replace("*", "")       # itálicas / listas con *
            .replace("- ", "")      # listas con guión
            .replace("\n\n", " ")   # párrafos dobles → espacio
            .replace("\n", " ")     # saltos de línea simples → espacio
            .replace("  ", " ")     # espacios dobles residuales
            .strip()
        )

        # Filtro final de caracteres de control para evitar JsonDecodeErrors en Flask
        clean_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', clean_text)

        if not clean_text:
            clean_text = "No pude generar una respuesta. Intenta reformular tu pregunta."

        return {"reply": clean_text, "status": "ok"}


    except Exception as exc:  # pylint: disable=broad-except
        # Logging explícito en consola para diagnóstico de 429s/403s
        error_msg_str = str(exc)
        print(f"\\n🚨 [ChatService Error] Tipo: {type(exc).__name__} | Detalles: {error_msg_str}\\n")
        logger.error("ChatService: Error al llamar a Gemini API: %s", exc)

        # MAS_ERROR_HANDLING_12: Interceptar 429 Rate Limit
        if "429" in error_msg_str or "Quota" in error_msg_str or "quota" in error_msg_str.lower():
            return {
                "reply": "¡Uf! Estoy recibiendo muchos mensajes a la vez 😅. Por favor, dame 1 minuto para tomar aire y vuelve a preguntarme.",
                "status": "rate_limit",
            }

        # Cualquier otro error (500, credenciales inválidas, etc)
        return {
            "reply": "Ups, tuve un pequeño mareo técnico. ¿Podemos intentar de nuevo en un momento?",
            "status": "api_error",
        }
