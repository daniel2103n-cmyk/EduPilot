"""
EduPilot — SavedRouteService
============================
Servicio de persistencia y gestión de rutas académicas guardadas por el estudiante.
Garantiza integridad referencial, instantáneas históricas y aislamiento de seguridad por estudiante.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.conf import settings

from apps.routes.models import SavedRoute, SavedRouteSemester, SavedRouteCourse
from services.route_generator import RouteResult

if TYPE_CHECKING:
    from apps.students.models import StudentProfile
    from apps.courses.models import Course


class SavedRouteService:
    """
    Operaciones CRUD y de consulta sobre rutas guardadas por el estudiante.
    """

    @classmethod
    @transaction.atomic
    def save_route(
        cls,
        student: 'StudentProfile',
        route_result: RouteResult,
        name: str = '',
        is_favorite: bool = False,
    ) -> SavedRoute:
        """
        Persiste un RouteResult en la base de datos como una instantánea histórica coherente.
        """
        if not student or not student.program:
            raise ValueError("El estudiante debe tener un programa académico asociado para guardar rutas.")

        if not name:
            name = f"Ruta {route_result.strategy_label}"

        # Periodo actual por defecto
        current_period = getattr(settings, 'CURRENT_ACADEMIC_PERIOD', '2025-1')

        # Si se marca como favorita, desmarcar las existentes
        if is_favorite:
            SavedRoute.objects.filter(student=student).update(is_favorite=False)
        elif not SavedRoute.objects.filter(student=student, is_favorite=True).exists():
            # Si es la primera ruta que guarda, hacerla favorita por defecto
            is_favorite = True

        saved_route = SavedRoute.objects.create(
            student=student,
            program=student.program,
            name=name.strip()[:200],
            strategy_key=route_result.strategy,
            strategy_label=route_result.strategy_label,
            is_favorite=is_favorite,
            estimated_semesters=route_result.estimated_semesters,
            total_credits=route_result.total_credits,
            total_courses=route_result.total_courses,
            is_within_ideal_limit=route_result.is_within_ideal_limit,
            over_limit_semesters=route_result.over_limit_semesters,
            academic_period=current_period,
            metadata={
                'over_limit_factors': route_result.over_limit_factors,
                'warnings': route_result.warnings,
                'metrics': route_result.metrics,
                'passed_count': route_result.passed_count,
                'pending_count': route_result.pending_count,
                'failed_count': route_result.failed_count,
                'critical_courses': route_result.critical_courses,
            }
        )

        # Crear semestres y materias snapshot
        for sem in route_result.semesters:
            saved_sem = SavedRouteSemester.objects.create(
                route=saved_route,
                semester_number=sem.number,
                total_credits=sem.total_credits,
            )
            for course in sem.courses:
                SavedRouteCourse.objects.create(
                    semester=saved_sem,
                    course=course,
                    course_code_snapshot=course.code,
                    course_name_snapshot=course.name,
                    credits_snapshot=course.credits,
                    level_snapshot=course.level,
                )

        return saved_route

    @classmethod
    def get_student_routes(cls, student: 'StudentProfile'):
        """Obtiene todas las rutas guardadas pertenecientes al estudiante."""
        return (
            SavedRoute.objects
            .filter(student=student)
            .select_related('program')
            .prefetch_related('semesters__courses__course')
            .order_by('-is_favorite', '-created_at')
        )

    @classmethod
    def get_route_for_student(cls, student: 'StudentProfile', route_id: int) -> SavedRoute:
        """Obtiene una ruta guardada específica asegurando que pertenezca al estudiante."""
        route = (
            SavedRoute.objects
            .filter(id=route_id, student=student)
            .select_related('program')
            .prefetch_related('semesters__courses__course')
            .first()
        )
        if not route:
            raise PermissionDenied("La ruta no existe o no tienes permisos para acceder a ella.")
        return route

    @classmethod
    def set_favorite(cls, student: 'StudentProfile', route_id: int) -> SavedRoute:
        """Establece una ruta como favorita del estudiante."""
        route = cls.get_route_for_student(student, route_id)
        route.mark_as_favorite()
        return route

    @classmethod
    def delete_route(cls, student: 'StudentProfile', route_id: int) -> bool:
        """Elimina una ruta propia garantizando control de acceso."""
        route = cls.get_route_for_student(student, route_id)
        was_fav = route.is_favorite
        route.delete()

        # Si era favorita y quedan otras, marcar la más reciente como favorita
        if was_fav:
            next_route = SavedRoute.objects.filter(student=student).order_by('-updated_at').first()
            if next_route:
                next_route.mark_as_favorite()

        return True

    @classmethod
    def get_active_or_default_route(cls, student: 'StudentProfile') -> SavedRoute | None:
        """Devuelve la ruta favorita o la más reciente del estudiante."""
        fav = SavedRoute.objects.filter(student=student, is_favorite=True).first()
        if fav:
            return fav
        return SavedRoute.objects.filter(student=student).order_by('-created_at').first()

    @classmethod
    def get_semester_courses(cls, saved_route: SavedRoute, semester_index: int = 1) -> list['Course']:
        """
        Retorna la lista de instancias de Course previstas para el semestre N de la ruta.
        Por defecto, el semestre 1 (que corresponde al semestre actual a cursar).
        """
        sem = saved_route.semesters.filter(semester_number=semester_index).first()
        if not sem:
            return []
        return [sc.course for sc in sem.courses.select_related('course').all()]
