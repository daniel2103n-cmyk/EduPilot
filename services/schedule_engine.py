"""
EduPilot — ScheduleEngine
=========================
Motor de planificación, validación, optimización y evaluación de calidad de horarios semestrales.

Responsabilidades:
  - Agrupar sesiones de CourseGroup por grupo/sección (un grupo puede tener múltiples bloques semanales).
  - Validar compatibilidad estricta (detección matemática de cruces/solapamientos por día y franja horaria).
  - Evaluar métricas de carga (horas semanales, días de asistencia, huecos/tiempos muertos, jornadas diarias).
  - Calcular puntuación de calidad explicable y generar advertencias transparentes.
  - Generar hasta 3 recomendaciones horarias diferenciadas (Compacta, Equilibrada, Mínimos Huecos).
  - Validar combinaciones personalizadas por el estudiante.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from django.conf import settings

if TYPE_CHECKING:
    from apps.courses.models import Course, CourseGroup
    from apps.students.models import StudentProfile


# Días canónicos ordenados
DAYS_ORDER = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
DAY_INDEX = {day: idx for idx, day in enumerate(DAYS_ORDER)}


@dataclass
class ScheduleSession:
    """Representa una sesión individual de clase dentro de una semana."""
    day: str
    start_time: datetime.time
    end_time: datetime.time
    classroom: str = '--'
    group_id: int | None = None

    @property
    def duration_minutes(self) -> int:
        start_min = self.start_time.hour * 60 + self.start_time.minute
        end_min = self.end_time.hour * 60 + self.end_time.minute
        return max(0, end_min - start_min)

    @property
    def duration_hours(self) -> float:
        return round(self.duration_minutes / 60.0, 1)

    def overlaps_with(self, other: 'ScheduleSession') -> bool:
        """
        Dos sesiones se solapan si ocurren el mismo día y sus intervalos abiertos se intersecan:
        start_A < end_B and end_A > start_B.
        Clases consecutivas (ej. 10:00-12:00 y 12:00-14:00) NO se solapan.
        """
        if self.day != other.day:
            return False
        return (self.start_time < other.end_time) and (self.end_time > other.start_time)


@dataclass
class CourseGroupOption:
    """
    Agrupa todas las sesiones que componen un grupo de una materia
    (ej. Cálculo I - Grupo SIS 101 con sesión Martes y Jueves).
    """
    course_id: int
    course_code: str
    course_name: str
    credits: int
    group_number: str
    available_spots: int
    semester: int
    sessions: list[ScheduleSession] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return f"{self.course_code} - Grupo {self.group_number}"

    @property
    def schedule_summary(self) -> str:
        if not self.sessions:
            return "Sin horario registrado"
        parts = []
        for s in self.sessions:
            st = s.start_time.strftime('%H:%M') if s.start_time else '--:--'
            et = s.end_time.strftime('%H:%M') if s.end_time else '--:--'
            parts.append(f"{s.day} {st}-{et}")
        return ", ".join(parts)


@dataclass
class ScheduleMetrics:
    """Métricas cuantitativas de la distribución semanal de un horario."""
    total_class_hours: float = 0.0
    total_weekly_wait_minutes: int = 0
    days_with_class: int = 0
    days_list: list[str] = field(default_factory=list)
    earliest_start: str = '--:--'
    latest_end: str = '--:--'
    longest_daily_stay_hours: float = 0.0
    longest_continuous_block_hours: float = 0.0
    hours_per_day: dict[str, float] = field(default_factory=dict)
    quality_score: int = 100
    warnings: list[str] = field(default_factory=list)


@dataclass
class ScheduleProposal:
    """Una propuesta u horario completo evaluado para las materias del semestre."""
    key: str                          # 'RECOMMENDED_COMPACT', 'RECOMMENDED_BALANCED', 'CUSTOM', etc.
    title: str
    description: str
    assigned_groups: list[CourseGroupOption] = field(default_factory=list)
    is_valid: bool = True
    conflicts: list[dict] = field(default_factory=list)
    metrics: ScheduleMetrics = field(default_factory=ScheduleMetrics)
    missing_courses: list[str] = field(default_factory=list)

    @property
    def total_credits(self) -> int:
        return sum(g.credits for g in self.assigned_groups)

    @property
    def courses_count(self) -> int:
        return len(self.assigned_groups)


class ScheduleEngine:
    """
    Motor Algorítmico de Horarios Académicos.
    """

    @classmethod
    def get_course_groups_catalog(
        cls,
        courses: list['Course'],
        current_semester: int | None = None
    ) -> dict[int, list[CourseGroupOption]]:
        """
        Consulta todos los grupos de la oferta académica para una lista de Course,
        agrupando sus distintas sesiones por (course_id, group_number).
        """
        from apps.courses.models import CourseGroup

        course_ids = [c.id for c in courses]
        course_codes = [c.code.strip() for c in courses]
        course_map_by_id = {c.id: c for c in courses}
        course_map_by_code = {c.code.strip().upper(): c for c in courses}

        # Filtrar grupos asociados por FK o por código
        from django.db.models import Q
        groups_qs = (
            CourseGroup.objects
            .filter(is_active=True)
            .filter(Q(course_id__in=course_ids) | Q(course_code__in=course_codes))
            .order_by('course_code', 'group_number', 'day', 'start_time')
        )

        catalog_by_course: dict[int, dict[str, CourseGroupOption]] = {c.id: {} for c in courses}

        for g in groups_qs:
            # Asociar a Course correspondiente
            matched_course = g.course or course_map_by_code.get(g.course_code.strip().upper())
            if not matched_course or matched_course.id not in catalog_by_course:
                continue

            cid = matched_course.id
            grp_num = str(g.group_number).strip()

            if grp_num not in catalog_by_course[cid]:
                catalog_by_course[cid][grp_num] = CourseGroupOption(
                    course_id=matched_course.id,
                    course_code=matched_course.code,
                    course_name=matched_course.name,
                    credits=matched_course.credits,
                    group_number=grp_num,
                    available_spots=g.available_spots,
                    semester=g.semester,
                    sessions=[]
                )

            if g.day and g.start_time and g.end_time:
                catalog_by_course[cid][grp_num].sessions.append(ScheduleSession(
                    day=g.day.strip(),
                    start_time=g.start_time,
                    end_time=g.end_time,
                    classroom=g.classroom or '--',
                    group_id=g.id
                ))

        # Convertir a lista de opciones por materia
        result = {}
        for cid, grps in catalog_by_course.items():
            result[cid] = list(grps.values())

        return result

    @classmethod
    def check_conflicts(cls, group_options: list[CourseGroupOption]) -> list[dict]:
        """
        Comprueba de forma exhaustiva si existen solapamientos entre las sesiones de los grupos seleccionados.
        """
        conflicts = []
        all_sessions: list[tuple[CourseGroupOption, ScheduleSession]] = []

        for grp in group_options:
            for session in grp.sessions:
                all_sessions.append((grp, session))

        n = len(all_sessions)
        for i in range(n):
            grp_a, sess_a = all_sessions[i]
            for j in range(i + 1, n):
                grp_b, sess_b = all_sessions[j]
                # Si pertenecen a la misma materia, no se comparan consigo mismos
                if grp_a.course_id == grp_b.course_id:
                    continue

                if sess_a.overlaps_with(sess_b):
                    st_a = sess_a.start_time.strftime('%H:%M')
                    et_a = sess_a.end_time.strftime('%H:%M')
                    st_b = sess_b.start_time.strftime('%H:%M')
                    et_b = sess_b.end_time.strftime('%H:%M')
                    conflicts.append({
                        'course_a': grp_a.course_name,
                        'group_a': grp_a.group_number,
                        'time_a': f"{sess_a.day} {st_a}-{et_a}",
                        'course_b': grp_b.course_name,
                        'group_b': grp_b.group_number,
                        'time_b': f"{sess_b.day} {st_b}-{et_b}",
                        'day': sess_a.day,
                    })

        return conflicts

    @classmethod
    def evaluate_metrics(cls, group_options: list[CourseGroupOption]) -> ScheduleMetrics:
        """
        Calcula las métricas de calidad de carga horaria semanal.
        """
        metrics = ScheduleMetrics()

        sessions_by_day: dict[str, list[ScheduleSession]] = {d: [] for d in DAYS_ORDER}
        total_class_min = 0

        for grp in group_options:
            for s in grp.sessions:
                if s.day in sessions_by_day:
                    sessions_by_day[s.day].append(s)
                    total_class_min += s.duration_minutes

        metrics.total_class_hours = round(total_class_min / 60.0, 1)

        active_days = []
        earliest_time = datetime.time(23, 59)
        latest_time = datetime.time(0, 0)
        total_wait_min = 0
        longest_daily_stay = 0
        longest_block = 0
        warnings = []
        hours_per_day = {}

        for day in DAYS_ORDER:
            day_sessions = sorted(sessions_by_day[day], key=lambda x: x.start_time)
            if not day_sessions:
                continue

            active_days.append(day)
            day_class_min = sum(s.duration_minutes for s in day_sessions)
            hours_per_day[day] = round(day_class_min / 60.0, 1)

            d_start = day_sessions[0].start_time
            d_end = day_sessions[-1].end_time

            if d_start < earliest_time:
                earliest_time = d_start
            if d_end > latest_time:
                latest_time = d_end

            # Tiempo de permanencia total en el día
            day_stay_min = (d_end.hour * 60 + d_end.minute) - (d_start.hour * 60 + d_start.minute)
            if day_stay_min > longest_daily_stay:
                longest_daily_stay = day_stay_min

            # Huecos y bloques continuos
            curr_block_min = day_sessions[0].duration_minutes
            for k in range(len(day_sessions) - 1):
                cur_s = day_sessions[k]
                next_s = day_sessions[k + 1]

                gap = (next_s.start_time.hour * 60 + next_s.start_time.minute) - (cur_s.end_time.hour * 60 + cur_s.end_time.minute)
                if gap > 0:
                    total_wait_min += gap
                    if gap >= 180:
                        warnings.append(f"Hueco prolongado de {round(gap/60, 1)}h el día {day} entre {cur_s.end_time.strftime('%H:%M')} y {next_s.start_time.strftime('%H:%M')}.")
                    curr_block_min = next_s.duration_minutes
                else:
                    curr_block_min += next_s.duration_minutes

                if curr_block_min > longest_block:
                    longest_block = curr_block_min

            if curr_block_min > longest_block:
                longest_block = curr_block_min

            if day_stay_min > 8 * 60:
                warnings.append(f"Jornada muy extensa el {day}: permanencia de {round(day_stay_min/60, 1)} horas.")

        if longest_block >= 360:
            warnings.append(f"Bloque continuo de clases sin descanso de {round(longest_block/60, 1)} horas.")

        metrics.days_with_class = len(active_days)
        metrics.days_list = active_days
        metrics.total_weekly_wait_minutes = total_wait_min
        metrics.longest_daily_stay_hours = round(longest_daily_stay / 60.0, 1)
        metrics.longest_continuous_block_hours = round(longest_block / 60.0, 1)
        metrics.hours_per_day = hours_per_day
        metrics.earliest_start = earliest_time.strftime('%H:%M') if active_days else '--:--'
        metrics.latest_end = latest_time.strftime('%H:%M') if active_days else '--:--'

        # Puntuación de calidad explicable (100 puntos base)
        score = 100
        # Penalizar huecos excesivos (-1 punto cada 30 min de hueco)
        score -= min(35, total_wait_min // 30)
        # Penalizar jornadas excesivas > 8h
        if longest_daily_stay > 8 * 60:
            score -= 15
        # Penalizar bloque continuo > 5h
        if longest_block > 5 * 60:
            score -= 10
        # Bonificar días libres si la carga lo permite (ej. 4 días)
        if 0 < len(active_days) <= 4:
            score += 5

        metrics.quality_score = max(30, min(100, score))
        metrics.warnings = warnings

        return metrics

    @classmethod
    def generate_recommendations(
        cls,
        courses: list['Course'],
        current_semester: int | None = None
    ) -> list[ScheduleProposal]:
        """
        Genera hasta tres recomendaciones horarias viables y distintas:
          1. Jornada compacta (terminar temprano o menos días).
          2. Distribución equilibrada (horas homogéneas entre días).
          3. Mínimos huecos (menor tiempo de espera).
        """
        if not courses:
            return []

        catalog = cls.get_course_groups_catalog(courses, current_semester)
        missing_courses = []
        valid_courses = []

        for c in courses:
            if not catalog.get(c.id):
                missing_courses.append(c.name)
            else:
                valid_courses.append(c)

        if not valid_courses:
            return [
                ScheduleProposal(
                    key='NO_OFFER',
                    title='Sin Oferta de Horarios',
                    description='No se encontraron grupos vigentes registrados para las materias solicitadas.',
                    is_valid=False,
                    missing_courses=missing_courses
                )
            ]

        # Búsqueda combinatoria acotada con poda de conflictos
        combos = cls._find_valid_combinations(valid_courses, catalog, max_combinations=40)

        if not combos:
            return [
                ScheduleProposal(
                    key='CONFLICT_DETECTED',
                    title='Conflicto de Horarios Inevitable',
                    description='Las opciones de grupos existentes para estas asignaturas colisionan entre sí.',
                    is_valid=False,
                    missing_courses=missing_courses
                )
            ]

        # Evaluar cada combinación válida
        evaluated = []
        for combo in combos:
            m = cls.evaluate_metrics(combo)
            evaluated.append((combo, m))

        proposals: list[ScheduleProposal] = []

        # 1. Recomendación Compacta: menor cantidad de días y fin más temprano
        compact_sorted = sorted(
            evaluated,
            key=lambda x: (x[1].days_with_class, x[1].latest_end, -x[1].quality_score)
        )
        best_compact = compact_sorted[0]
        proposals.append(ScheduleProposal(
            key='COMPACT',
            title='Jornada Compacta',
            description='Prioriza menos días de asistencia a la universidad y finalización más temprana.',
            assigned_groups=best_compact[0],
            is_valid=True,
            metrics=best_compact[1],
            missing_courses=missing_courses
        ))

        # 2. Recomendación Mínimos Huecos: menor tiempo de espera entre clases
        least_gaps_sorted = sorted(
            evaluated,
            key=lambda x: (x[1].total_weekly_wait_minutes, -x[1].quality_score)
        )
        best_gaps = least_gaps_sorted[0]
        # Evitar duplicar exactamente la misma combinación
        if cls._is_different_combination(best_compact[0], best_gaps[0]) or len(evaluated) == 1:
            proposals.append(ScheduleProposal(
                key='MIN_GAPS',
                title='Tiempo Continuo (Mínimos Huecos)',
                description='Minimiza las horas muertas o pausas largas entre clases dentro de la misma jornada.',
                assigned_groups=best_gaps[0],
                is_valid=True,
                metrics=best_gaps[1],
                missing_courses=missing_courses
            ))

        # 3. Recomendación Equilibrada: mejor balance general de puntuación
        balanced_sorted = sorted(
            evaluated,
            key=lambda x: (-x[1].quality_score, x[1].longest_daily_stay_hours)
        )
        best_balanced = balanced_sorted[0]
        if all(cls._is_different_combination(p.assigned_groups, best_balanced[0]) for p in proposals):
            proposals.append(ScheduleProposal(
                key='BALANCED',
                title='Distribución Equilibrada',
                description='Reparte armoniosamente las horas de clase de la semana evitando saturación diaria.',
                assigned_groups=best_balanced[0],
                is_valid=True,
                metrics=best_balanced[1],
                missing_courses=missing_courses
            ))

        return proposals

    @classmethod
    def validate_custom_combination(
        cls,
        selected_groups: list[CourseGroupOption]
    ) -> ScheduleProposal:
        """
        Valida una combinación seleccionada manualmente por el estudiante.
        """
        conflicts = cls.check_conflicts(selected_groups)
        metrics = cls.evaluate_metrics(selected_groups)
        is_valid = len(conflicts) == 0

        return ScheduleProposal(
            key='CUSTOM',
            title='Horario Personalizado',
            description='Combinación ajustada por el estudiante.',
            assigned_groups=selected_groups,
            is_valid=is_valid,
            conflicts=conflicts,
            metrics=metrics
        )

    # ─────────────────────────────────────────────────────────────────────────
    # BÚSQUEDA COMBINATORIA CON PODA
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def _find_valid_combinations(
        cls,
        courses: list['Course'],
        catalog: dict[int, list[CourseGroupOption]],
        max_combinations: int = 50
    ) -> list[list[CourseGroupOption]]:
        """
        Algoritmo DFS de backtracking con poda anticipada de conflictos.
        """
        results: list[list[CourseGroupOption]] = []

        def backtrack(course_idx: int, current_selection: list[CourseGroupOption]):
            if len(results) >= max_combinations:
                return

            if course_idx >= len(courses):
                results.append(list(current_selection))
                return

            course = courses[course_idx]
            options = catalog.get(course.id, [])
            if not options:
                # Si una materia no tiene grupos, intentamos avanzar con las demás
                backtrack(course_idx + 1, current_selection)
                return

            for opt in options:
                # Poda: comprobar si este grupo choca con alguno ya seleccionado
                has_clash = False
                for existing in current_selection:
                    for s_new in opt.sessions:
                        for s_ext in existing.sessions:
                            if s_new.overlaps_with(s_ext):
                                has_clash = True
                                break
                        if has_clash:
                            break
                    if has_clash:
                        break

                if not has_clash:
                    current_selection.append(opt)
                    backtrack(course_idx + 1, current_selection)
                    current_selection.pop()

        backtrack(0, [])
        return results

    @classmethod
    def _is_different_combination(
        cls,
        combo_a: list[CourseGroupOption],
        combo_b: list[CourseGroupOption]
    ) -> bool:
        set_a = {(g.course_id, g.group_number) for g in combo_a}
        set_b = {(g.course_id, g.group_number) for g in combo_b}
        return set_a != set_b
