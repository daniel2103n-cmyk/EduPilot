"""
EduPilot — RouteGeneratorService
=================================
Servicio de generación de rutas académicas para estudiantes.

Responsabilidades:
  - Calcular materias disponibles según prerrequisitos aprobados
  - Proyectar la ruta COMPLETA hacia el futuro (iteración semestre por semestre)
  - Aplicar una estrategia de carga académica (FastTrack / Balanced / Light)
  - Devolver un RouteResult estructurado listo para renderizar en el template

Estrategias:
  FAST_TRACK  → máxima carga, terminar lo antes posible (hasta 7 materias/sem)
  BALANCED    → carga estándar universitaria (hasta 5 materias/sem)  ← default
  LIGHT       → carga mínima, ideal para trabajar o recuperar promedio (hasta 4)

Algoritmo de proyección completa:
  La ruta NO solo muestra las materias disponibles HOY.
  Simula semestre a semestre: las materias planeadas en el semestre N se
  consideran "aprobadas virtualmente" para desbloquear el semestre N+1,
  dando así una ruta completa hasta terminar el programa.

NO usa IA, ML ni algoritmos complejos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.students.models import StudentProfile


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

class Strategy:
    FAST_TRACK = 'FAST_TRACK'
    BALANCED   = 'BALANCED'
    LIGHT      = 'LIGHT'

    LABELS = {
        FAST_TRACK: 'Fast Track',
        BALANCED:   'Balanceada',
        LIGHT:      'Ligera',
    }

    DESCRIPTIONS = {
        FAST_TRACK: 'Carga máxima — terminar el programa lo antes posible.',
        BALANCED:   'Carga estándar — equilibrio entre avance y bienestar.',
        LIGHT:      'Carga mínima — ideal para quienes trabajan o buscan mejorar el promedio.',
    }

    # Materias por semestre según estrategia
    MAX_COURSES = {
        FAST_TRACK: 7,
        BALANCED:   5,
        LIGHT:      4,
    }

    # Créditos máximos por semester
    MAX_CREDITS = {
        FAST_TRACK: 18,
        BALANCED:   18,
        LIGHT:      14,
    }

    ALL = [FAST_TRACK, BALANCED, LIGHT]


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES — resultado estructurado
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RouteSemester:
    """Un semestre dentro de la ruta recomendada."""
    number:        int                    # número de semestre futuro (1-based)
    courses:       list        = field(default_factory=list)   # lista de Course
    total_credits: int         = 0


@dataclass
class RouteResult:
    """Resultado completo devuelto por RouteGeneratorService.generate()."""
    strategy:          str                          # Strategy.FAST_TRACK | ...
    strategy_label:    str
    strategy_desc:     str
    semesters:         list[RouteSemester] = field(default_factory=list)

    # Métricas
    total_courses:     int  = 0
    total_credits:     int  = 0
    estimated_semesters: int = 0

    # Estado académico previo (informativo)
    passed_count:      int  = 0
    pending_count:     int  = 0

    # Errores / avisos
    error:             str  = ''

    @property
    def is_empty(self) -> bool:
        return self.total_courses == 0

    @property
    def difficulty_label(self) -> str:
        """Texto de dificultad estimada según estrategia."""
        return {
            Strategy.FAST_TRACK: 'Alta',
            Strategy.BALANCED:   'Media',
            Strategy.LIGHT:      'Baja',
        }.get(self.strategy, '—')

    @property
    def difficulty_color(self) -> str:
        """Clase CSS para el badge de dificultad."""
        return {
            Strategy.FAST_TRACK: 'error',
            Strategy.BALANCED:   'tertiary',
            Strategy.LIGHT:      'secondary',
        }.get(self.strategy, 'outline')


# ─────────────────────────────────────────────────────────────────────────────
# SERVICIO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class RouteGeneratorService:
    """
    Genera una ruta académica COMPLETA para un StudentProfile dado.

    Uso:
        from services.route_generator import RouteGeneratorService, Strategy

        result = RouteGeneratorService.generate(profile, strategy=Strategy.BALANCED)

    El resultado es un RouteResult con TODOS los semestres proyectados
    hasta completar el programa, no solo los inmediatamente disponibles.
    """

    @classmethod
    def generate(
        cls,
        profile: 'StudentProfile',
        strategy: str = Strategy.BALANCED,
    ) -> RouteResult:
        """
        Punto de entrada público.

        Pasos:
          1. Obtener materias aprobadas (passed_ids) e in_progress (in_progress_ids)
          2. Obtener todas las materias pendientes del programa
          3. Proyectar la ruta COMPLETA iterativamente:
             - Semestre 1: materias desbloqueadas con passed_ids actuales
             - Semestre 2: desbloqueadas después de aprobar el semestre 1
             - ... hasta que no queden materias pendientes
          4. Calcular métricas globales
        """
        if strategy not in Strategy.ALL:
            strategy = Strategy.BALANCED

        result = RouteResult(
            strategy=strategy,
            strategy_label=Strategy.LABELS[strategy],
            strategy_desc=Strategy.DESCRIPTIONS[strategy],
        )

        # Validación temprana
        if profile is None:
            result.error = 'No se encontró perfil de estudiante.'
            return result

        if not profile.program_id:
            result.error = 'No tienes un programa académico asignado.'
            return result

        # ── Importaciones diferidas para evitar circular imports ─────────────
        from apps.academic.models import AcademicRecord
        from apps.courses.models import Course

        # ── 1. Estado académico actual ───────────────────────────────────────
        records = AcademicRecord.objects.filter(student=profile)

        passed_ids = set(
            records.filter(status='PASSED').values_list('course_id', flat=True)
        )
        in_progress_ids = set(
            records.filter(status='IN_PROGRESS').values_list('course_id', flat=True)
        )
        # Materias ya tomadas (no volver a planearlas)
        taken_ids = passed_ids | in_progress_ids

        result.passed_count = len(passed_ids)

        # ── 2. Materias pendientes del programa ──────────────────────────────
        pending_courses = list(
            Course.objects
            .filter(program=profile.program, is_active=True)
            .exclude(id__in=taken_ids)
            .prefetch_related('course_prerequisites__required_course')
            .order_by('level', '-credits', 'name')
        )

        result.pending_count = len(pending_courses)

        if not pending_courses:
            # ¡El estudiante ya completó todo el programa!
            result.error = (
                '¡Felicitaciones! No tienes materias pendientes. '
                'Has completado todas las materias de tu programa.'
            )
            return result

        # ── 3. Proyección iterativa de la ruta completa ──────────────────────
        # virtual_passed_ids arranca con las materias realmente aprobadas.
        # A medida que planificamos semestres, añadimos las materias planeadas
        # para desbloquear las siguientes.
        result.semesters = cls._project_full_route(
            pending_courses=pending_courses,
            initial_passed_ids=passed_ids,
            in_progress_ids=in_progress_ids,
            strategy=strategy,
        )

        # ── 4. Calcular métricas globales ────────────────────────────────────
        result.total_courses       = sum(len(s.courses) for s in result.semesters)
        result.total_credits       = sum(s.total_credits for s in result.semesters)
        result.estimated_semesters = len(result.semesters)

        if result.total_courses == 0:
            result.error = (
                'No hay materias disponibles con los prerrequisitos actuales. '
                'Aprueba más materias para desbloquear nuevas rutas.'
            )

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # PROYECCIÓN COMPLETA ITERATIVA
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def _project_full_route(
        cls,
        pending_courses: list,
        initial_passed_ids: set,
        in_progress_ids: set,
        strategy: str,
    ) -> list[RouteSemester]:
        """
        Proyecta la ruta académica completa iterando semestre por semestre.

        Algoritmo:
          - virtual_passed = aprobadas reales + en_progreso (se asume que pasan)
          - En cada iteración busca qué cursos se desbloquean con virtual_passed
          - Los agrupa en un semestre según la estrategia
          - Los añade a virtual_passed y los elimina de remaining
          - Repite hasta que no haya más cursos disponibles o remaining esté vacío
          - Máximo 20 semestres (guard para evitar loops infinitos)

        Args:
            pending_courses:     Lista de Course aún no tomados.
            initial_passed_ids:  IDs de materias realmente aprobadas.
            in_progress_ids:     IDs de materias actualmente en curso (se
                                 consideran como "casi aprobadas" para proyectar).
            strategy:            Estrategia de carga.

        Returns:
            Lista de RouteSemester con todos los semestres proyectados.
        """
        max_courses = Strategy.MAX_COURSES[strategy]
        max_credits = Strategy.MAX_CREDITS[strategy]
        MAX_SEMESTERS = 20  # Guard de seguridad

        semesters: list[RouteSemester] = []

        # Partimos de aprobadas + en_progreso como base de desbloqueo
        virtual_passed: set = initial_passed_ids | in_progress_ids

        # Mapa prereq por curso (precalculado una sola vez)
        prereq_map: dict[int, set] = {
            course.id: set(
                course.course_prerequisites.values_list('required_course_id', flat=True)
            )
            for course in pending_courses
        }

        remaining = list(pending_courses)  # Copia mutable

        sem_number = 1
        while remaining and sem_number <= MAX_SEMESTERS:
            # Cursos desbloqueados en este momento virtual
            available = [
                c for c in remaining
                if prereq_map[c.id].issubset(virtual_passed)
            ]

            if not available:
                # No se pueden desbloquear más materias — prerrequisitos cíclicos
                # o data inconsistente. Terminamos la proyección.
                break

            # Llenar el semestre respetando los límites de la estrategia
            semester = RouteSemester(number=sem_number)
            courses_placed_ids: set = set()

            for course in available:
                if len(semester.courses) >= max_courses:
                    break
                if semester.total_credits + course.credits > max_credits:
                    continue  # Saltar esta, intentar la siguiente (menor crédito)
                semester.courses.append(course)
                semester.total_credits += course.credits
                courses_placed_ids.add(course.id)

            if not semester.courses:
                # Ningún curso cabe (todos superan el límite de créditos)
                # Añadir al menos uno para evitar loop infinito
                course = available[0]
                semester.courses.append(course)
                semester.total_credits += course.credits
                courses_placed_ids.add(course.id)

            semesters.append(semester)

            # Los cursos planeados ahora "pasan" virtualmente
            virtual_passed |= courses_placed_ids

            # Remover los planeados de la lista restante
            remaining = [c for c in remaining if c.id not in courses_placed_ids]

            sem_number += 1

        return semesters

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODO LEGADO (mantenido por compatibilidad, no usado en generate())
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _filter_available(pending_courses, passed_ids: set) -> list:
        """
        Devuelve solo las materias cuyos prerrequisitos están todos aprobados.
        Usado internamente por _project_full_route.
        """
        available = []
        for course in pending_courses:
            prereq_ids = set(
                course.course_prerequisites.values_list('required_course_id', flat=True)
            )
            if prereq_ids.issubset(passed_ids):
                available.append(course)
        return available
