"""
EduPilot — Prompt para explicación de rutas académicas.
Genera instrucciones estructuradas para el modelo de IA.
El modelo explica la trayectoria calculada objetivamente por el motor.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.route_generator import RouteResult
    from apps.students.models import StudentProfile


SYSTEM_PROMPT = """\
Eres EduPilot-AI, un consejero académico universitario especializado en planificación curricular y trayectorias formativas.
Tu función es EXPLICAR detallada, empática y profesionalmente la ruta académica calculada por el motor algorítmico del sistema.
NUNCA inventes notas, calificaciones, nombres de materias inexistentes ni alteres la secuencia calculada.

Debes responder siempre en español y organizar tu análisis obligatoriamente en estas 7 secciones numeradas:

1. **Resumen de la estrategia**: Explica brevemente el enfoque de esta alternativa y su ritmo de avance.
2. **Explicación de la trayectoria**: Describe la progresión académica a mediano y largo plazo.
3. **Análisis de los semestres**: Comenta la carga de créditos y materias en los ciclos iniciales e intermedios.
4. **Materias críticas y dependencias**: Menciona las materias cuello de botella que desbloquean más asignaturas o requieren mayor atención.
5. **Ventajas y desventajas**: Señala con objetividad los beneficios y los sacrificios de cursar a este ritmo.
6. **Riesgos o restricciones**: Evalúa el margen ideal institucional de 10 semestres (indicando si la ruta está dentro del margen o si proyecta sobrepermanencia y sus causas), fatiga académica o prerrequisitos en serie.
7. **Recomendación final**: Consejo personalizado de estudio para el estudiante según las métricas calculadas.
"""


def build_route_prompt(profile: 'StudentProfile', route: 'RouteResult') -> str:
    """Construye el prompt del usuario con el contexto curricular exhaustivo."""
    # Desglose de semestres proyectados
    semesters_detail = []
    for s in route.semesters[:4]:  # Primeros 4 semestres para contexto claro
        course_names = [f"{c.code} {c.name} ({c.credits} cr)" for c in s.courses]
        semesters_detail.append(
            f"  - Semestre {s.number} ({s.total_credits} cr, {len(s.courses)} materias): " + ", ".join(course_names)
        )
    if len(route.semesters) > 4:
        semesters_detail.append(f"  - (... y {len(route.semesters) - 4} semestre(s) proyectado(s) adicionales).")

    semesters_str = "\n".join(semesters_detail) if semesters_detail else "  (Sin semestres proyectados)"

    # Materias críticas
    crit_str = "Ninguna identificada como cuello de botella inmediato."
    if route.critical_courses:
        crit_str = ", ".join(
            f"{c['code']} {c['name']} (desbloquea {c['unlock_count']} materias{' - REPROBADA' if c.get('is_failed') else ''})"
            for c in route.critical_courses[:4]
        )

    # Margen de 10 semestres
    ideal_status = (
        "DENTRO DEL MARGEN IDEAL (<= 10 semestres de carrera)."
        if route.is_within_ideal_limit
        else f"SUPERA EL MARGEN IDEAL por {route.over_limit_semesters} semestre(s). Factores: {'; '.join(route.over_limit_factors)}"
    )

    return f"""\
DATOS DEL ESTUDIANTE:
- Programa Académico: {profile.program.name if profile.program else 'No asignado'}
- Semestre actual en curso: Semestre {profile.current_semester}
- Materias aprobadas: {route.passed_count}
- Materias actualmente en curso: {route.in_progress_count}
- Materias reprobadas pendientes de aprobación: {route.failed_count}
- Total materias pendientes por cursar: {route.pending_count}

RUTA GENERADA POR EL MOTOR:
- Estrategia: {route.strategy_label} ({route.strategy})
- Duración proyectada: {route.estimated_semesters} semestres
- Total créditos a cursar: {route.total_credits} créditos
- Total asignaturas incluidas: {route.total_courses}
- Carga promedio por semestre: {route.average_credits_per_semester} créditos
- Cumplimiento de margen institucional de 10 semestres: {ideal_status}
- Asignaturas críticas con mayor cadena de desbloqueo: {crit_str}

PROYECCIÓN POR SEMESTRES:
{semesters_str}

Por favor, genera la explicación completa organizada en las 7 secciones requeridas.
"""