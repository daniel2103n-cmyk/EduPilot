"""
EduPilot — Prompt para explicación de horarios semanales.
Genera instrucciones estructuradas para el modelo de IA.
El modelo explica la distribución horaria calculada objetivamente por el motor.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.schedule_engine import ScheduleProposal
    from apps.students.models import StudentProfile


SYSTEM_PROMPT = """\
Eres EduPilot-AI, un asesor académico y de bienestar universitario especializado en organización del tiempo y horarios de clase.
Tu función es EXPLICAR la distribución semanal del horario de clases calculado por el motor algorítmico para el semestre vigente.
NUNCA inventes grupos, salones inexistentes ni asegures disponibilidad de cupos que el sistema no haya validado.

Debes responder siempre en español y organizar tu análisis obligatoriamente en estas 6 secciones numeradas:

1. **Resumen de la distribución semanal**: Describe cómo están repartidas las horas de clase de lunes a viernes y cuántos días requiere asistencia presencial.
2. **Ventajas de esta combinación**: Destaca los puntos fuertes (ej. días libres, jornadas compactas o baja dispersión).
3. **Días y jornadas más exigentes**: Analiza los días con mayor carga horaria o permanencia en campus y la hora de inicio más temprana.
4. **Análisis de huecos y tiempos de espera**: Comenta los intervalos entre clases y sugiere cómo aprovecharlos para estudio autónomo o descanso.
5. **Recomendaciones de ajuste y hábitos**: Brinda consejos prácticos sobre desplazamientos, alimentación y estudio para este horario.
6. **Advertencias y consideraciones**: Señala cualquier alerta sobre jornadas continuas sin descanso o salidas tardías.
"""


def build_schedule_prompt(profile: 'StudentProfile', proposal: 'ScheduleProposal') -> str:
    """Construye el prompt con las métricas y distribución semanal del horario."""
    # Desglose de asignaturas y grupos
    courses_lines = []
    for grp in proposal.assigned_groups:
        sess_str = grp.schedule_summary
        courses_lines.append(f"  • {grp.course_name} (Grupo {grp.group_number}, {grp.credits} cr): {sess_str}")

    courses_detail = "\n".join(courses_lines) if courses_lines else "  (Sin materias asignadas)"

    m = proposal.metrics
    hours_per_day_str = ", ".join(f"{d}: {h}h" for d, h in m.hours_per_day.items()) if m.hours_per_day else "Sin clases"
    warnings_str = "; ".join(m.warnings) if m.warnings else "Sin advertencias de sobrecarga horaria."

    return f"""\
DATOS DEL ESTUDIANTE:
- Programa: {profile.program.name if profile.program else 'No asignado'}
- Semestre vigente: {profile.current_semester}

PROPUESTA DE HORARIO ({proposal.title}):
- Total créditos matriculados: {proposal.total_credits}
- Cantidad de asignaturas: {proposal.courses_count}
- Horas totales de clase semanal: {m.total_class_hours} horas
- Días de asistencia con clase: {m.days_with_class} días ({', '.join(m.days_list)})
- Carga por día: {hours_per_day_str}
- Hora más temprana de inicio: {m.earliest_start} | Hora más tardía de salida: {m.latest_end}
- Jornada diaria más extensa: {m.longest_daily_stay_hours} horas de permanencia
- Bloque continuo más largo: {m.longest_continuous_block_hours} horas seguidas
- Tiempo de espera semanal en huecos: {round(m.total_weekly_wait_minutes / 60, 1)} horas ({m.total_weekly_wait_minutes} min)
- Puntuación de calidad calculada: {m.quality_score} / 100
- Alertas detectadas por el motor: {warnings_str}

ASIGNATURAS Y SESIONES:
{courses_detail}

Por favor, genera la explicación completa del horario organizada en las 6 secciones requeridas.
"""
