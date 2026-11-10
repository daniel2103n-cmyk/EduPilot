"""
EduPilot — Servicio de Inteligencia Artificial (Renovado).

Soporta inferencia local mediante Ollama (predeterminado: qwen3.5:4b)
y compatibilidad con OpenRouter API (modelo remoto).

Responsabilidades:
  - Invocar al proveedor configurado con prompts especializados para Rutas y Horarios.
  - Explicación de rutas académicas a largo plazo (7 secciones estructuradas).
  - Explicación de horarios semanales vigentes (6 secciones estructuradas con métricas reales).
  - Manejo integral de errores, límites de tiempo y fallbacks analíticos enriquecidos.
  - No exponer datos sensibles ni depender de la IA para la validez de los algoritmos.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import requests

if TYPE_CHECKING:
    from services.route_generator import RouteResult
    from services.schedule_engine import ScheduleProposal
    from apps.students.models import StudentProfile

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT_MODEL = "openrouter/free"

# Timeouts
OLLAMA_TIMEOUT = (3, 60)
OPENROUTER_TIMEOUT = (5, 25)

# Parámetros de inferencia
OLLAMA_TEMPERATURE = 0.6
OLLAMA_NUM_PREDICT = 450  # Permitir longitud adecuada para las 7 secciones

OPENROUTER_TEMPERATURE = 0.7
OPENROUTER_MAX_TOKENS = 600


class AIService:
    """
    Cliente unificado para generación de explicaciones académicas mediante IA.
    Ofrece dos servicios especializados:
      1. explain_route()   -> Explicación curricular a largo plazo.
      2. explain_schedule()-> Explicación de distribución horaria semanal.
    """

    def __init__(self):
        self._load_config()

    def _load_config(self) -> None:
        """Carga la configuración desde Django settings de forma segura."""
        try:
            from django.conf import settings
            self.provider = getattr(settings, 'AI_PROVIDER', 'ollama').strip().lower()
            self.ollama_base_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
            self.ollama_model = getattr(settings, 'OLLAMA_MODEL', 'qwen3.5:4b').strip()
            self.openrouter_api_key = getattr(settings, 'OPENROUTER_API_KEY', '').strip()
            self.openrouter_model = getattr(settings, 'OPENROUTER_MODEL', OPENROUTER_DEFAULT_MODEL)
        except Exception:
            self.provider = 'ollama'
            self.ollama_base_url = 'http://localhost:11434'
            self.ollama_model = 'qwen3.5:4b'
            self.openrouter_api_key = ''
            self.openrouter_model = OPENROUTER_DEFAULT_MODEL

    @property
    def current_model_name(self) -> str:
        self._load_config()
        if self.provider == 'ollama':
            return f"Qwen 3.5 (Ollama: {self.ollama_model})"
        return f"OpenRouter ({self.openrouter_model})"

    # ─────────────────────────────────────────────────────────────────────────
    # 1. IA DE RUTAS ACADÉMICAS
    # ─────────────────────────────────────────────────────────────────────────

    def explain_route(
        self,
        profile: 'StudentProfile',
        route: 'RouteResult',
    ) -> str:
        """
        Genera una explicación exhaustiva en lenguaje natural de la ruta académica.
        """
        if not route or route.is_empty:
            return (
                "No hay materias pendientes para proyectar en este momento. "
                "Has completado tu plan curricular o tu historial académico requiere actualización."
            )

        from apps.ai.prompts.route_explanier import SYSTEM_PROMPT, build_route_prompt

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_route_prompt(profile, route)},
        ]

        self._load_config()
        response_text = self._send_request(messages)

        if not response_text:
            # Fallback analítico estructurado basado en las métricas reales
            return self._build_route_fallback(route)

        return response_text

    # ─────────────────────────────────────────────────────────────────────────
    # 2. IA DE HORARIOS SEMANALES
    # ─────────────────────────────────────────────────────────────────────────

    def explain_schedule(
        self,
        profile: 'StudentProfile',
        proposal: 'ScheduleProposal',
    ) -> str:
        """
        Genera una explicación detallada de la distribución semanal de clases y su calidad.
        """
        if not proposal or not proposal.assigned_groups:
            return (
                "No hay grupos seleccionados para evaluar en este horario. "
                "Selecciona una ruta guardada y consulta las recomendaciones disponibles."
            )

        from apps.ai.prompts.schedule_explainer import SYSTEM_PROMPT, build_schedule_prompt

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_schedule_prompt(profile, proposal)},
        ]

        self._load_config()
        response_text = self._send_request(messages)

        if not response_text:
            return self._build_schedule_fallback(proposal)

        return response_text

    # ─────────────────────────────────────────────────────────────────────────
    # DISPATCHER DE PETICIONES (OLLAMA / OPENROUTER)
    # ─────────────────────────────────────────────────────────────────────────

    def _send_request(self, messages: list[dict[str, str]]) -> str | None:
        """Envía la solicitud al proveedor configurado y devuelve el texto o None si falla."""
        try:
            if self.provider == 'ollama':
                return self._call_ollama(messages)
            elif self.provider == 'openrouter':
                return self._call_openrouter(messages)
            else:
                return self._call_ollama(messages)
        except Exception as exc:
            logger.warning("[AIService] Fallo en proveedor '%s': %s", self.provider, exc)
            return None

    def _call_ollama(self, messages: list[dict[str, str]]) -> str | None:
        url = f"{self.ollama_base_url}/api/chat"
        payload = {
            "model": self.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": OLLAMA_NUM_PREDICT,
                "temperature": OLLAMA_TEMPERATURE,
            },
        }

        try:
            response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "").strip()
            return content if content else None
        except Exception as exc:
            logger.info("[AIService] Ollama no disponible localmente (%s). Aplicando respuesta analítica estructurada.", exc)
            return None

    def _call_openrouter(self, messages: list[dict[str, str]]) -> str | None:
        if not self.openrouter_api_key:
            return None

        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://edupilot.app",
            "X-Title": "EduPilot",
        }
        payload = {
            "model": self.openrouter_model,
            "messages": messages,
            "temperature": OPENROUTER_TEMPERATURE,
            "max_tokens": OPENROUTER_MAX_TOKENS,
        }

        try:
            response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=OPENROUTER_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return content if content else None
        except Exception as exc:
            logger.warning("[AIService] OpenRouter no respondió: %s", exc)
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # FALLBACKS ANALÍTICOS (FAIL-SAFE ESTRUCTURADOS)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_route_fallback(self, route: 'RouteResult') -> str:
        """Construye una explicación sólida en 7 secciones cuando la IA externa no está en línea."""
        ideal_note = (
            f"La ruta se proyecta a {route.estimated_semesters} semestres, manteniéndose dentro del margen ideal de referencia institucional."
            if route.is_within_ideal_limit
            else f"La trayectoria supera el margen ideal institucional de 10 semestres en {route.over_limit_semesters} ciclo(s). Factores asociados: {'; '.join(route.over_limit_factors)}."
        )

        crit_names = [f"{c['code']} ({c['name']})" for c in route.critical_courses[:3]]
        crit_text = f"Asignaturas clave con mayor impacto de desbloqueo: {', '.join(crit_names)}." if crit_names else "Distribución sin cuellos de botella severos."

        return f"""\
1. **Resumen de la estrategia**:
Esta alternativa aplica el criterio de '{route.strategy_label}', orientada a estructurar un avance curricular ordenado según los prerrequisitos aprobados y pendientes de tu programa.

2. **Explicación de la trayectoria**:
La proyección contempla un total de {route.total_courses} materias distribuidas a lo largo de {route.estimated_semesters} semestres, sumando {route.total_credits} créditos académicos con una carga promedio de {route.average_credits_per_semester} créditos por ciclo.

3. **Análisis de los semestres**:
Los primeros semestres priorizan materias de nivel inicial y asignaturas que habilitan ramas curriculares posteriores, estabilizando la carga para evitar concentraciones excesivas.

4. **Materias críticas y dependencias**:
{crit_text} Superar estas materias en el primer intento es fundamental para mantener el ritmo programado.

5. **Ventajas y desventajas**:
- *Ventajas*: Secuencia 100% validada sin colisiones de prerrequisitos y ritmo adaptado a tu estrategia.
- *Desventajas*: Exige estricto cumplimiento del plan, ya que reprobar asignaturas troncales desplaza los semestres posteriores.

6. **Riesgos o restricciones**:
{ideal_note} Recuerda que esta proyección asume aprobación continua de los créditos matriculados.

7. **Recomendación final**:
Te recomendamos inscribir las asignaturas del primer semestre proyectado y utilizar el planificador de horarios de EduPilot para seleccionar secciones sin cruces horarios.
"""

    def _build_schedule_fallback(self, proposal: 'ScheduleProposal') -> str:
        """Construye una explicación detallada de horario cuando la IA externa no está en línea."""
        m = proposal.metrics
        days_str = ", ".join(m.days_list) if m.days_list else "Sin días asignados"
        hours_str = ", ".join(f"{d} ({h}h)" for d, h in m.hours_per_day.items())
        gaps_hours = round(m.total_weekly_wait_minutes / 60.0, 1)
        courses_names = [f"{g.course_name} (G{g.group_number})" for g in proposal.assigned_groups]
        courses_list_str = f" Asignaturas incluidas: {', '.join(courses_names)}." if courses_names else ""

        return f"""\
1. **Resumen de la distribución semanal**:
El horario propuesto para '{proposal.title}' reúne {proposal.courses_count} asignaturas ({proposal.total_credits} créditos) con un total de {m.total_class_hours} horas de clase distribuidas en {m.days_with_class} días ({days_str}).{courses_list_str}

2. **Ventajas de esta combinación**:
Ofrece una combinación validada por el motor sin cruces de horarios. Carga diaria: {hours_str}. Calificación de calidad: {m.quality_score}/100.

3. **Días y jornadas más exigentes**:
La hora más temprana de inicio es a las {m.earliest_start} y la jornada más prolongada tiene una permanencia máxima de {m.longest_daily_stay_hours} horas en el campus.

4. **Análisis de huecos y tiempos de espera**:
El horario registra {gaps_hours} horas totales de tiempo de espera semanal entre clases. Se recomienda aprovechar estos intervalos para trabajo en biblioteca o estudio autónomo.

5. **Recomendaciones de ajuste y hábitos**:
Planifica tus traslados con anticipación considerando los días con clase a primera hora y mantén horarios regulares de alimentación.

6. **Advertencias y consideraciones**:
{' '.join(m.warnings) if m.warnings else 'No se detectaron jornadas críticas ni sobrecargas continuas.'}
"""


ai_service = AIService()