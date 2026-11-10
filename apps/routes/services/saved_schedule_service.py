"""
EduPilot — SavedScheduleService
===============================
Servicio para guardar, consultar, validar y actualizar horarios semestrales del estudiante.
Permite vincularlos con la ruta de origen y verificar vigencia frente a la oferta de CourseGroup.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.conf import settings

from apps.routes.models import SavedSchedule, SavedScheduleItem, SavedRoute
from apps.courses.models import Course, CourseGroup
from services.schedule_engine import ScheduleProposal, CourseGroupOption

if TYPE_CHECKING:
    from apps.students.models import StudentProfile


class SavedScheduleService:
    """Gestión de persistencia de horarios semestrales."""

    @classmethod
    @transaction.atomic
    def save_proposal(
        cls,
        student: 'StudentProfile',
        proposal: ScheduleProposal,
        name: str = 'Mi Horario Semestral',
        saved_route: SavedRoute | None = None,
    ) -> SavedSchedule:
        """
        Guarda una propuesta u horario personalizado en la BD.
        Solo se guarda como is_valid=True si la propuesta no tiene cruces.
        """
        if not student:
            raise ValueError("Se requiere el perfil del estudiante para guardar un horario.")

        current_period = getattr(settings, 'CURRENT_ACADEMIC_PERIOD', '2025-1')

        metrics_dict = {
            'quality_score': proposal.metrics.quality_score,
            'total_class_hours': proposal.metrics.total_class_hours,
            'total_weekly_wait_minutes': proposal.metrics.total_weekly_wait_minutes,
            'days_with_class': proposal.metrics.days_with_class,
            'days_list': proposal.metrics.days_list,
            'earliest_start': proposal.metrics.earliest_start,
            'latest_end': proposal.metrics.latest_end,
            'longest_daily_stay_hours': proposal.metrics.longest_daily_stay_hours,
            'hours_per_day': proposal.metrics.hours_per_day,
            'warnings': proposal.metrics.warnings,
            'total_credits': proposal.total_credits,
            'courses_count': proposal.courses_count,
        }

        schedule = SavedSchedule.objects.create(
            student=student,
            saved_route=saved_route,
            name=name.strip()[:200] or 'Mi Horario Semestral',
            academic_period=current_period,
            is_valid=proposal.is_valid,
            is_pending_review=False,
            metrics=metrics_dict,
        )

        for grp in proposal.assigned_groups:
            course = Course.objects.filter(id=grp.course_id).first()
            if not course:
                continue

            sessions_data = []
            for s in grp.sessions:
                sessions_data.append({
                    'day': s.day,
                    'start_time': s.start_time.strftime('%H:%M') if s.start_time else '--:--',
                    'end_time': s.end_time.strftime('%H:%M') if s.end_time else '--:--',
                    'classroom': s.classroom,
                })

            SavedScheduleItem.objects.create(
                schedule=schedule,
                course=course,
                course_code_snapshot=grp.course_code,
                course_name_snapshot=grp.course_name,
                group_number=grp.group_number,
                credits_snapshot=grp.credits,
                sessions_snapshot=sessions_data,
            )

        return schedule

    @classmethod
    def get_student_schedules(cls, student: 'StudentProfile'):
        """Retorna todos los horarios guardados del estudiante autenticado."""
        return (
            SavedSchedule.objects
            .filter(student=student)
            .select_related('saved_route')
            .prefetch_related('items__course')
            .order_by('-updated_at')
        )

    @classmethod
    def get_schedule_for_student(cls, student: 'StudentProfile', schedule_id: int) -> SavedSchedule:
        """Obtiene un horario específico con validación estricta de propiedad."""
        schedule = (
            SavedSchedule.objects
            .filter(id=schedule_id, student=student)
            .select_related('saved_route')
            .prefetch_related('items__course')
            .first()
        )
        if not schedule:
            raise PermissionDenied("El horario no existe o no tienes permisos para acceder a él.")
        return schedule

    @classmethod
    def delete_schedule(cls, student: 'StudentProfile', schedule_id: int) -> bool:
        """Elimina un horario guardado propio."""
        schedule = cls.get_schedule_for_student(student, schedule_id)
        schedule.delete()
        return True

    @classmethod
    def check_offer_changes(cls, schedule: SavedSchedule) -> dict:
        """
        Compara los grupos guardados en el horario con la oferta vigente de CourseGroup.
        Detecta si algún grupo ya no está activo o si cambió de horario.
        """
        changes = {
            'has_changes': False,
            'missing_groups': [],
            'modified_sessions': [],
        }

        for item in schedule.items.all():
            active_groups = CourseGroup.objects.filter(
                course_code__iexact=item.course_code_snapshot,
                group_number__iexact=item.group_number,
                is_active=True
            )
            if not active_groups.exists():
                changes['missing_groups'].append(f"{item.course_name_snapshot} (G{item.group_number})")
                changes['has_changes'] = True

        if changes['has_changes'] and not schedule.is_pending_review:
            schedule.is_pending_review = True
            schedule.save(update_fields=['is_pending_review'])

        return changes
