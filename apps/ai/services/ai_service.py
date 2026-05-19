"""
EduPilot — Servicio de Inteligencia Artificial.

Integración real con OpenRouter API usando mistralai/mistral-7b-instruct.

Responsabilidades:
  - Llamar a OpenRouter con los prompts construidos en /prompts/
  - Manejar errores de red, autenticación y límites de la API
  - Devolver siempre un string (nunca lanzar excepción al caller)

La IA NO genera rutas académicas — eso lo hace RouteGeneratorService.
La IA SOLO explica y justifica las rutas calculadas por Django.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from services.route_generator import RouteResult
    from apps.students.models import StudentProfile

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL   = "openrouter/free"

# Timeout total de la petición HTTP (segundos)
REQUEST_TIMEOUT = 25

# Temperatura: 0.7 → respuestas naturales pero coherentes
TEMPERATURE = 0.7

# Máximo de tokens en la respuesta (3 secciones cortas ~250 tokens bastan)
MAX_TOKENS = 350


# ─────────────────────────────────────────────────────────────────────────────
# MENSAJES DE FALLBACK
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_NO_ROUTE = (
    "No hay materias disponibles para explicar en este momento. "
    "Asegúrate de tener tu historial académico actualizado."
)

_FALLBACK_NO_KEY = (
    "La explicación de IA no está disponible: falta configurar "
    "la API key de OpenRouter en el servidor."
)

_FALLBACK_ERROR = (
    "No se pudo obtener la explicación de IA en este momento. "
    "La ruta fue calculada correctamente — intenta de nuevo más tarde."
)


# ─────────────────────────────────────────────────────────────────────────────
# SERVICIO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class AIService:
    """
    Cliente HTTP para OpenRouter API.

    Uso:
        from apps.ai.services.ai_service import ai_service

        explanation = ai_service.explain_route(profile, route)
    """

    def __init__(self):
        from django.conf import settings
        self.api_key = getattr(settings, 'OPENROUTER_API_KEY', '').strip()
        self.model   = OPENROUTER_MODEL

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODO PÚBLICO
    # ─────────────────────────────────────────────────────────────────────────

    def explain_route(
        self,
        profile:  'StudentProfile',
        route:    'RouteResult',
    ) -> str:
        """
        Genera una explicación en lenguaje natural de la ruta académica.

        Args:
            profile: StudentProfile del estudiante.
            route:   RouteResult calculado por RouteGeneratorService.

        Returns:
            str: Explicación generada por Mistral-7B, o mensaje de fallback.
                 Nunca lanza excepciones al caller.
        """
        # Guardia: ruta vacía
        if route.is_empty:
            logger.info("[AIService] explain_route: ruta vacía, devolviendo fallback")
            return _FALLBACK_NO_ROUTE

        # Guardia: sin API key configurada
        if not self.api_key:
            logger.warning("[AIService] OPENROUTER_API_KEY no configurada")
            return _FALLBACK_NO_KEY

        # Construir mensajes
        from apps.ai.prompts.route_explanier import SYSTEM_PROMPT, build_route_prompt

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_route_prompt(profile, route)},
        ]

        try:
            return self._call_openrouter(messages)

        except requests.exceptions.Timeout:
            logger.error("[AIService] Timeout al llamar a OpenRouter")
            return _FALLBACK_ERROR

        except requests.exceptions.ConnectionError:
            logger.error("[AIService] Error de conexión con OpenRouter")
            return _FALLBACK_ERROR

        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            if status_code in (401, 403):
                logger.error("[AIService] API Key inválida o sin permisos (HTTP %s)", status_code)
                return (
                    "La explicación de IA no está disponible: la API key de OpenRouter "
                    "es inválida o no tiene permisos. Contacta al administrador."
                )
            if status_code == 429:
                logger.error("[AIService] Límite de peticiones alcanzado (HTTP 429)")
                return (
                    "La explicación de IA no está disponible en este momento debido a que se ha "
                    "alcanzado el límite de peticiones del modelo gratuito. Intenta de nuevo en unos minutos."
                )
            logger.error("[AIService] HTTPError de OpenRouter: %s", exc)
            return _FALLBACK_ERROR

        except Exception as exc:                        # noqa: BLE001
            logger.exception("[AIService] Error inesperado: %s", exc)
            return _FALLBACK_ERROR

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODO PRIVADO — HTTP
    # ─────────────────────────────────────────────────────────────────────────

    def _call_openrouter(self, messages: list) -> str:
        """
        Realiza la llamada HTTP a OpenRouter y extrae el texto de la respuesta.

        Raises:
            requests.exceptions.* si ocurre un error de red o HTTP.
            ValueError si la respuesta no tiene el formato esperado.
        """
        headers = {
            "Authorization":  f"Bearer {self.api_key}",
            "Content-Type":   "application/json",
            # Cabeceras recomendadas por OpenRouter para ranking/analytics
            "HTTP-Referer":   "https://edupilot.app",
            "X-Title":        "EduPilot",
        }

        payload = {
            "model":       self.model,
            "messages":    messages,
            "temperature": TEMPERATURE,
            "max_tokens":  MAX_TOKENS,
        }

        logger.info("[AIService] Enviando request a OpenRouter (model=%s)", self.model)

        response = requests.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

        # Lanzar excepción si el status code indica error (4xx / 5xx)
        response.raise_for_status()

        data = response.json()

        # Extraer texto generado
        try:
            content = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            logger.error("[AIService] Respuesta inesperada de OpenRouter: %s", data)
            raise ValueError(f"Formato de respuesta inválido: {exc}") from exc

        logger.info("[AIService] Respuesta recibida (%d chars)", len(content))
        return content


# ─────────────────────────────────────────────────────────────────────────────
# SINGLETON — importar desde otros módulos con:
#   from apps.ai.services.ai_service import ai_service
# ─────────────────────────────────────────────────────────────────────────────

ai_service = AIService()