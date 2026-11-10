"""
EduPilot — RouteGeneratorService (Renovado)
===========================================
Servicio integral de generación y optimización de rutas académicas para estudiantes.

Responsabilidades:
  - Analizar historial académico real (aprobadas, reprobadas, en curso, pendientes).
  - Resolver dependencias y prerrequisitos curriculares.
  - Detectar ciclos inválidos en el grafo de prerrequisitos.
  - Proyectar semestres futuros mediante algoritmos de planificación académica con criterios diferenciados.
  - Evaluar cumplimiento frente al margen ideal institucional de 10 semestres.
  - Generar hasta 3 alternativas fundamentadas (Acelerada, Equilibrada, Flexible).
  - Detectar y descartar rutas duplicadas.
  - Producir un RouteResult estructurado rico en métricas para interfaz e IA.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from django.conf import settings

if TYPE_CHECKING:
    from apps.students.models import StudentProfile
    from apps.courses.models import Course

logger = logging.getLogger(__name__)

# Margen ideal institucional de duración (configurable, por defecto 10 semestres)
DEFAULT_IDEAL_SEMESTERS = getattr(settings, 'IDEAL_SEMESTERS_LIMIT', 10)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES Y ESTRATEGIAS
# ─────────────────────────────────────────────────────────────────────────────

class Strategy:
    FAST_TRACK = 'FAST_TRACK'
    BALANCED   = 'BALANCED'
    LIGHT      = 'LIGHT'

    LABELS = {
        FAST_TRACK: 'Avance Acelerado',
        BALANCED:   'Distribución Equilibrada',
        LIGHT:      'Planificación Flexible',
    }

    DESCRIPTIONS = {
        FAST_TRACK: 'Prioriza desbloquear dependencias y reducir la duración total proyectada dentro de los límites seguros.',
        BALANCED:   'Equilibrio óptimo entre avance académico y carga de créditos por semestre.',
        LIGHT:      'Carga gradual moderada, ideal para conciliar trabajo, actividades extracurriculares o bienestar.',
    }

    # Restricciones máximas por estrategia
    MAX_COURSES = {
        FAST_TRACK: 7,
        BALANCED:   6,
        LIGHT:      5,
    }

    # Tope DURO de créditos por semestre: ninguna estrategia puede superar 18 cr.
    MAX_CREDITS = {
        FAST_TRACK: 18,  # límite institucional: máx 18 cr. por semestre
        BALANCED:   18,
        LIGHT:      16,
    }

    TARGET_CREDITS = {
        FAST_TRACK: 18,
        BALANCED:   16,
        LIGHT:      14,
    }

    ALL = [FAST_TRACK, BALANCED, LIGHT]


# ─────────────────────────────────────────────────────────────────────────────
# MODELOS DE DATOS ESTRUCTURADOS (DATA CLASSES)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RouteSemester:
    """Un semestre dentro de la ruta recomendada."""
    number:        int                     # 1-based futuro
    courses:       list = field(default_factory=list)  # lista de instancias de Course
    total_credits: int  = 0

    @property
    def semester_number(self) -> int:
        """Alias para compatibilidad con plantillas."""
        return self.number

    @property
    def courses_count(self) -> int:
        return len(self.courses)


@dataclass
class RouteResult:
    """Resultado completo y estructurado producido por el motor de rutas."""
    strategy:            str                           # Strategy.FAST_TRACK | ...
    strategy_label:      str
    strategy_desc:       str
    semesters:           list[RouteSemester] = field(default_factory=list)

    # Métricas cuantitativas
    total_courses:       int  = 0
    total_credits:       int  = 0
    estimated_semesters: int = 0

    # Margen ideal institucional (10 semestres)
    ideal_limit:         int  = DEFAULT_IDEAL_SEMESTERS
    is_within_ideal_limit: bool = True
    over_limit_semesters: int = 0
    over_limit_factors:  list[str] = field(default_factory=list)

    # Estado académico previo
    passed_count:        int  = 0
    pending_count:       int  = 0
    failed_count:        int  = 0
    in_progress_count:   int  = 0

    # Análisis curricular y advertencias
    critical_courses:    list[dict] = field(default_factory=list)
    warnings:            list[str] = field(default_factory=list)
    metrics:             dict = field(default_factory=dict)

    # Errores técnicos o validaciones
    error:               str  = ''

    @property
    def total_semesters(self) -> int:
        """Alias para compatibilidad con templates previos."""
        return self.estimated_semesters

    @property
    def is_empty(self) -> bool:
        return self.total_courses == 0

    @property
    def average_credits_per_semester(self) -> float:
        if self.estimated_semesters == 0:
            return 0.0
        return round(self.total_credits / self.estimated_semesters, 1)

    @property
    def difficulty_label(self) -> str:
        return {
            Strategy.FAST_TRACK: 'Alta exigencia',
            Strategy.BALANCED:   'Moderada / Equilibrada',
            Strategy.LIGHT:      'Flexible / Gradual',
        }.get(self.strategy, 'Estándar')

    @property
    def difficulty_color(self) -> str:
        return {
            Strategy.FAST_TRACK: 'error',
            Strategy.BALANCED:   'secondary',
            Strategy.LIGHT:      'tertiary',
        }.get(self.strategy, 'outline')

    @property
    def signature(self) -> tuple:
        """Firma única para comparar igualdad estructural entre rutas."""
        sig = []
        for s in self.semesters:
            c_ids = tuple(sorted(c.id for c in s.courses))
            sig.append((s.number, c_ids))
        return tuple(sig)


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR PRINCIPAL DE RUTAS
# ─────────────────────────────────────────────────────────────────────────────

class RouteGeneratorService:
    """
    Motor Algorítmico de Rutas Académicas de EduPilot.
    """

    @classmethod
    def generate(
        cls,
        profile: 'StudentProfile',
        strategy: str = Strategy.BALANCED,
    ) -> RouteResult:
        """Genera una alternativa específica según la estrategia indicada."""
        if strategy not in Strategy.ALL:
            strategy = Strategy.BALANCED

        result = RouteResult(
            strategy=strategy,
            strategy_label=Strategy.LABELS[strategy],
            strategy_desc=Strategy.DESCRIPTIONS[strategy],
            ideal_limit=DEFAULT_IDEAL_SEMESTERS,
        )

        if profile is None:
            result.error = 'No se encontró el perfil del estudiante.'
            return result

        if not profile.program_id:
            result.error = 'No tienes un programa académico asignado para planificar rutas.'
            return result

        from apps.academic.models import AcademicRecord
        from apps.courses.models import Course, Prerequisite

        # 1. Consultar registros académicos reales
        records = AcademicRecord.objects.filter(student=profile)
        passed_ids = set(records.filter(status='PASSED').values_list('course_id', flat=True))
        in_progress_ids = set(records.filter(status='IN_PROGRESS').values_list('course_id', flat=True))
        failed_ids = set(records.filter(status='FAILED').values_list('course_id', flat=True)) - passed_ids

        result.passed_count = len(passed_ids)
        result.in_progress_count = len(in_progress_ids)
        result.failed_count = len(failed_ids)

        # Asignaturas ya aprobadas o actualmente en curso no se programan de nuevo
        taken_ids = passed_ids | in_progress_ids

        # 2. Catálogo de materias pendientes del programa
        pending_courses = list(
            Course.objects
            .filter(program=profile.program, is_active=True)
            .exclude(id__in=taken_ids)
            .prefetch_related('course_prerequisites__required_course')
            .order_by('level', 'name')
        )
        result.pending_count = len(pending_courses)

        if not pending_courses:
            result.error = (
                '¡Felicitaciones! Has completado todas las asignaturas correspondientes a tu plan de estudios.'
            )
            return result

        # 3. Construir grafo y mapa de dependencias
        all_program_courses = list(Course.objects.filter(program=profile.program, is_active=True))
        prereqs_qs = Prerequisite.objects.filter(course__program=profile.program)
        
        prereq_map: dict[int, set[int]] = {c.id: set() for c in all_program_courses}
        dependents_map: dict[int, set[int]] = {c.id: set() for c in all_program_courses}

        for pr in prereqs_qs:
            if pr.course_id in prereq_map and pr.required_course_id in dependents_map:
                prereq_map[pr.course_id].add(pr.required_course_id)
                dependents_map[pr.required_course_id].add(pr.course_id)

        # 4. Validar detección de ciclos en dependencias
        cycle_detected, cycle_path = cls._detect_dependency_cycles(prereq_map, pending_courses)
        if cycle_detected:
            result.error = (
                f"Conflicto curricular detectado en la malla académica: existe un ciclo de dependencias "
                f"entre las asignaturas ({' -> '.join(cycle_path)}). Notifica a coordinación académica."
            )
            logger.error("[RouteGenerator] Ciclo de dependencias detectado: %s", cycle_path)
            return result

        # 5. Calcular impacto de desbloqueo (número de materias dependientes directas e indirectas)
        unlock_scores = cls._calculate_unlock_scores(dependents_map)

        # Materias críticas
        crit_courses = []
        for c in pending_courses:
            score = unlock_scores.get(c.id, 0)
            if score >= 2 or c.id in failed_ids:
                crit_courses.append({
                    'course_id': c.id,
                    'code': c.code,
                    'name': c.name,
                    'unlock_count': score,
                    'is_failed': c.id in failed_ids,
                    'level': c.level,
                    'credits': c.credits,
                })
        crit_courses.sort(key=lambda x: (not x['is_failed'], -x['unlock_count'], x['level']))
        result.critical_courses = crit_courses[:8]

        # 6. Proyección estructurada de la ruta
        semesters, warnings = cls._project_route(
            pending_courses=pending_courses,
            initial_passed_ids=passed_ids,
            in_progress_ids=in_progress_ids,
            failed_ids=failed_ids,
            prereq_map=prereq_map,
            unlock_scores=unlock_scores,
            strategy=strategy,
        )

        result.semesters = semesters
        result.warnings = warnings
        result.total_courses = sum(len(s.courses) for s in semesters)
        result.total_credits = sum(s.total_credits for s in semesters)
        result.estimated_semesters = len(semesters)

        if result.total_courses == 0:
            result.error = (
                'No fue posible construir una secuencia válida con los prerrequisitos actuales. '
                'Verifica tu historial de materias aprobadas.'
            )
            return result

        # 7. Evaluación del margen ideal de 10 semestres
        current_sem = profile.current_semester or 1
        total_career_projection = (current_sem - 1) + result.estimated_semesters

        if result.estimated_semesters > DEFAULT_IDEAL_SEMESTERS or total_career_projection > DEFAULT_IDEAL_SEMESTERS:
            result.is_within_ideal_limit = False
            result.over_limit_semesters = max(0, total_career_projection - DEFAULT_IDEAL_SEMESTERS)
            factors = []
            if result.failed_count > 0:
                factors.append(f"{result.failed_count} asignatura(s) reprobada(s) que retrasaron la cadena curricular.")
            if result.pending_count > 25:
                factors.append("Alto volumen de créditos y asignaturas pendientes acumuladas.")
            if strategy == Strategy.LIGHT:
                factors.append("Estrategia flexible con tope de 4 asignaturas y 14 créditos por periodo.")
            chain_len = cls._calculate_longest_prerequisite_chain(prereq_map, pending_courses)
            if chain_len > 4:
                factors.append(f"Cadena obligatoria de prerrequisitos en serie de al menos {chain_len} niveles sucesivos.")
            result.over_limit_factors = factors or ["Secuencia curricular obligatoria de dependencias."]
        else:
            result.is_within_ideal_limit = True
            result.over_limit_semesters = 0

        # Métricas de calidad
        result.metrics = {
            'avg_credits': result.average_credits_per_semester,
            'max_credits_in_a_sem': max((s.total_credits for s in semesters), default=0),
            'min_credits_in_a_sem': min((s.total_credits for s in semesters), default=0),
            'longest_chain_length': cls._calculate_longest_prerequisite_chain(prereq_map, pending_courses),
            'projected_career_semesters': total_career_projection,
        }

        return result

    @classmethod
    def generate_alternatives(cls, profile: 'StudentProfile') -> list[RouteResult]:
        """
        Genera hasta tres alternativas distintas (Acelerada, Equilibrada, Flexible).
        Descarta duplicados exactos y devuelve solo las rutas que aporten variabilidad real.
        """
        raw_results = [
            cls.generate(profile, Strategy.FAST_TRACK),
            cls.generate(profile, Strategy.BALANCED),
            cls.generate(profile, Strategy.LIGHT),
        ]

        # Filtrar rutas que arrojaron error grave si al menos una funcionó
        valid_results = [r for r in raw_results if not r.error]
        if not valid_results:
            return raw_results[:1]

        unique_routes: list[RouteResult] = []
        seen_signatures = set()

        for r in valid_results:
            sig = r.signature
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                unique_routes.append(r)

        return unique_routes

    # ─────────────────────────────────────────────────────────────────────────
    # ALGORITMOS DE PROYECCIÓN Y RESTRICCIONES
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def _project_route(
        cls,
        pending_courses: list['Course'],
        initial_passed_ids: set[int],
        in_progress_ids: set[int],
        failed_ids: set[int],
        prereq_map: dict[int, set[int]],
        unlock_scores: dict[int, int],
        strategy: str,
    ) -> tuple[list[RouteSemester], list[str]]:
        """
        Proyecta la secuencia iterativa semestre por semestre respetando prerrequisitos y límites de carga.
        """
        max_courses = Strategy.MAX_COURSES.get(strategy, 5)
        max_credits = Strategy.MAX_CREDITS.get(strategy, 18)
        target_credits = Strategy.TARGET_CREDITS.get(strategy, 15)
        MAX_SAFETY_SEMESTERS = 20

        semesters: list[RouteSemester] = []
        warnings: list[str] = []

        # Estado de materias aprobadas virtualmente a medida que avanzamos en la proyección
        virtual_passed = set(initial_passed_ids) | set(in_progress_ids)
        remaining = list(pending_courses)

        sem_number = 1
        while remaining and sem_number <= MAX_SAFETY_SEMESTERS:
            # 1. Asignaturas cuyos prerrequisitos ya se satisfacen
            available = [c for c in remaining if prereq_map.get(c.id, set()).issubset(virtual_passed)]

            if not available:
                warnings.append(
                    f"Se detuvo la proyección en el semestre {sem_number}: quedan {len(remaining)} materia(s) "
                    f"cuyos prerrequisitos no pudieron ser desbloqueados."
                )
                break

            # 2. Ordenar candidatos según la estrategia:
            if strategy == Strategy.FAST_TRACK:
                # Priorizar reprobadas, materias con alto poder de desbloqueo, y nivel bajo
                available.sort(key=lambda c: (
                    0 if c.id in failed_ids else 1,
                    -unlock_scores.get(c.id, 0),
                    c.level,
                    -c.credits
                ))
            elif strategy == Strategy.LIGHT:
                # Carga suave: menor nivel, créditos moderados
                available.sort(key=lambda c: (
                    0 if c.id in failed_ids else 1,
                    c.level,
                    c.credits,
                    -unlock_scores.get(c.id, 0)
                ))
            else:  # BALANCED
                # Equilibrada: reprobadas primero, luego por nivel y balance de desbloqueos
                available.sort(key=lambda c: (
                    0 if c.id in failed_ids else 1,
                    c.level,
                    -unlock_scores.get(c.id, 0),
                    -c.credits
                ))

            # 3. Llenar el semestre
            semester = RouteSemester(number=sem_number)
            placed_ids: set[int] = set()

            for c in available:
                if len(semester.courses) >= max_courses:
                    break
                # Materias de 0 créditos (diagnósticas/nivelatorias) nunca bloquean el cupo de créditos
                if c.credits > 0 and semester.total_credits + c.credits > max_credits:
                    # Si ya estamos cerca del target de créditos, no forzar más materias
                    if semester.total_credits >= target_credits:
                        break
                    continue

                semester.courses.append(c)
                semester.total_credits += c.credits
                placed_ids.add(c.id)

            # Si ningún curso cupo por créditos pero había disponibles,
            # colocar al menos uno para no estancar la proyección,
            # pero RESPETANDO siempre el tope duro de 18 créditos.
            if not semester.courses and available:
                c = available[0]
                # Solo forzar si no supera el límite institucional absoluto de 18 cr.
                if semester.total_credits + c.credits <= 18:
                    semester.courses.append(c)
                    semester.total_credits += c.credits
                    placed_ids.add(c.id)
                else:
                    # La materia es demasiado pesada sola; añadirla sería ilegal.
                    # Agregar advertencia y detener la proyección para no crear
                    # semestres inválidos.
                    warnings.append(
                        f"Semestre {sem_number}: la materia '{c.name}' ({c.credits} cr.) no puede "
                        f"colocarse sin superar el límite de 18 créditos. Revisa el plan de estudios."
                    )
                    break

            semesters.append(semester)
            virtual_passed |= placed_ids
            remaining = [c for c in remaining if c.id not in placed_ids]
            sem_number += 1

        return semesters, warnings

    # ─────────────────────────────────────────────────────────────────────────
    # ANÁLISIS DE GRAFOS: CICLOS, DESBLOQUEOS Y CAMINOS CRÍTICOS
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def _detect_dependency_cycles(
        cls,
        prereq_map: dict[int, set[int]],
        pending_courses: list['Course']
    ) -> tuple[bool, list[str]]:
        """Detecta si hay algún ciclo en el subgrafo de prerrequisitos."""
        course_dict = {c.id: c.code for c in pending_courses}
        visited: dict[int, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        parent: dict[int, int] = {}
        cycle_nodes: list[int] = []

        def dfs(node: int) -> bool:
            visited[node] = 1
            for req in prereq_map.get(node, set()):
                if req not in visited:
                    visited[req] = 0
                if visited[req] == 1:
                    # Ciclo encontrado
                    curr = node
                    cycle_nodes.append(req)
                    while curr != req and curr in parent:
                        cycle_nodes.append(curr)
                        curr = parent[curr]
                    cycle_nodes.append(req)
                    cycle_nodes.reverse()
                    return True
                elif visited[req] == 0:
                    parent[req] = node
                    if dfs(req):
                        return True
            visited[node] = 2
            return False

        for c in pending_courses:
            if visited.get(c.id, 0) == 0:
                if dfs(c.id):
                    path_names = [course_dict.get(nid, str(nid)) for nid in cycle_nodes]
                    return True, path_names

        return False, []

    @classmethod
    def _calculate_unlock_scores(cls, dependents_map: dict[int, set[int]]) -> dict[int, int]:
        """Calcula cuántas materias en total (directas + indirectas) desbloquea cada curso."""
        scores: dict[int, int] = {}
        for course_id in dependents_map:
            visited: set[int] = set()
            stack = list(dependents_map[course_id])
            while stack:
                curr = stack.pop()
                if curr not in visited:
                    visited.add(curr)
                    stack.extend(dependents_map.get(curr, set()) - visited)
            scores[course_id] = len(visited)
        return scores

    @classmethod
    def _calculate_longest_prerequisite_chain(
        cls,
        prereq_map: dict[int, set[int]],
        pending_courses: list['Course']
    ) -> int:
        """Calcula la longitud de la cadena más larga de dependencias."""
        memo: dict[int, int] = {}
        pending_ids = {c.id for c in pending_courses}

        def get_depth(cid: int) -> int:
            if cid in memo:
                return memo[cid]
            reqs = prereq_map.get(cid, set()) & pending_ids
            if not reqs:
                memo[cid] = 1
                return 1
            max_d = 1 + max(get_depth(r) for r in reqs)
            memo[cid] = max_d
            return max_d

        return max((get_depth(c.id) for c in pending_courses), default=0)
