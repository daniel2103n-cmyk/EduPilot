"""
EduPilot — Prompt para explicación de rutas académicas.

Genera el par (system, user) que se envía a Mistral-7B.
El modelo SOLO explica — la ruta ya fue calculada por Django.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.route_generator import RouteResult
    from apps.students.models import StudentProfile


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — rol e instrucciones permanentes
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Eres EduPilot-AI, un asesor académico empático y profesional.
Tu única función es EXPLICAR rutas académicas que ya fueron calculadas \
por el sistema. NUNCA calculas ni cambias la ruta.

Reglas estrictas:
- Responde siempre en español.
- Usa un tono cercano, claro y motivador.
- Responde en exactamente 3 secciones con estos títulos exactos:
  **Ventajas de esta ruta**
  **Posibles riesgos**
  **¿Para qué tipo de estudiante es ideal?**
- Cada sección: máximo 2 oraciones.
- No uses listas de bullets dentro de las secciones.
- No repitas los datos técnicos que ya ve el estudiante en pantalla.
"""


# ─────────────────────────────────────────────────────────────────────────────
# USER PROMPT — datos dinámicos de la ruta
# ─────────────────────────────────────────────────────────────────────────────

def build_route_prompt(profile: 'StudentProfile', route: 'RouteResult') -> str:
    """
    Construye el mensaje del usuario con el contexto académico.

    Args:
        profile: StudentProfile del estudiante autenticado.
        route:   RouteResult calculado por RouteGeneratorService.

    Returns:
        str: Mensaje listo para enviarse como role='user'.
    """
    # Listar materias del primer semestre de la ruta (las más inmediatas)
    first_sem_courses = []
    if route.semesters:
        first_sem_courses = [
            f"{c.code} - {c.name} ({c.credits} créditos)"
            for c in route.semesters[0].courses
        ]

    courses_str = (
        "\n".join(f"  • {c}" for c in first_sem_courses)
        if first_sem_courses
        else "  (ninguna disponible)"
    )

    return f"""\
Analiza la siguiente ruta académica y genera tu explicación.

DATOS DEL ESTUDIANTE:
  Programa:         {profile.program}
  Semestre actual:  {profile.current_semester}
  Materias aprobadas hasta ahora: {route.passed_count}
  Materias pendientes en total:   {route.pending_count}

RUTA GENERADA ({route.strategy_label}):
  Duración estimada:   {route.estimated_semesters} semestre(s)
  Materias incluidas:  {route.total_courses}
  Créditos totales:    {route.total_credits}
  Dificultad:          {route.difficulty_label}

PRÓXIMAS MATERIAS (semestre 1 de la ruta):
{courses_str}

Genera tu explicación siguiendo exactamente el formato indicado.
"""