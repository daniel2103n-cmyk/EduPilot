"""
EduPilot — Pruebas Automatizadas del Motor de Horarios y ScheduleEngine
"""

import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.academic.models import AcademicProgram
from apps.courses.models import Course, CourseGroup
from apps.students.models import StudentProfile
from apps.routes.models import SavedSchedule, SavedScheduleItem
from apps.routes.services.saved_schedule_service import SavedScheduleService
from services.schedule_engine import (
    ScheduleEngine, ScheduleSession, CourseGroupOption, ScheduleProposal
)

User = get_user_model()


class ScheduleEngineTests(TestCase):
    """Pruebas algorítmicas de detección de cruces, métricas y recomendaciones."""

    def setUp(self):
        self.program = AcademicProgram.objects.create(name="Ingeniería de Software")
        self.user = User.objects.create_user(username="student_sched", password="password123")
        self.profile = StudentProfile.objects.create(user=self.user, program=self.program)

        self.c1 = Course.objects.create(name="Cálculo I", code="MAT101", credits=4, level=1, program=self.program)
        self.c2 = Course.objects.create(name="Física I", code="FIS101", credits=3, level=1, program=self.program)
        self.c3 = Course.objects.create(name="Programación I", code="SIS101", credits=3, level=1, program=self.program)

    def test_compatible_sessions_no_overlap(self):
        """1. Dos grupos que no se cruzan en horario."""
        grp1 = CourseGroupOption(
            course_id=self.c1.id, course_code="MAT101", course_name="Cálculo I", credits=4,
            group_number="1", available_spots=30, semester=1,
            sessions=[ScheduleSession(day="Lunes", start_time=datetime.time(7, 0), end_time=datetime.time(9, 0))]
        )
        grp2 = CourseGroupOption(
            course_id=self.c2.id, course_code="FIS101", course_name="Física I", credits=3,
            group_number="1", available_spots=30, semester=1,
            sessions=[ScheduleSession(day="Lunes", start_time=datetime.time(9, 0), end_time=datetime.time(11, 0))]
        )

        conflicts = ScheduleEngine.check_conflicts([grp1, grp2])
        self.assertEqual(len(conflicts), 0)

    def test_overlapping_sessions_detected(self):
        """2. Dos sesiones que se solapan en el mismo día."""
        grp1 = CourseGroupOption(
            course_id=self.c1.id, course_code="MAT101", course_name="Cálculo I", credits=4,
            group_number="1", available_spots=30, semester=1,
            sessions=[ScheduleSession(day="Martes", start_time=datetime.time(8, 0), end_time=datetime.time(10, 0))]
        )
        grp2 = CourseGroupOption(
            course_id=self.c2.id, course_code="FIS101", course_name="Física I", credits=3,
            group_number="1", available_spots=30, semester=1,
            sessions=[ScheduleSession(day="Martes", start_time=datetime.time(9, 0), end_time=datetime.time(11, 0))]
        )

        conflicts = ScheduleEngine.check_conflicts([grp1, grp2])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['day'], 'Martes')

    def test_multi_session_group(self):
        """3. Un grupo con varias sesiones semanales (Lunes y Miércoles)."""
        grp_multi = CourseGroupOption(
            course_id=self.c1.id, course_code="MAT101", course_name="Cálculo I", credits=4,
            group_number="SIS 101", available_spots=35, semester=1,
            sessions=[
                ScheduleSession(day="Lunes", start_time=datetime.time(7, 0), end_time=datetime.time(9, 0)),
                ScheduleSession(day="Miércoles", start_time=datetime.time(7, 0), end_time=datetime.time(9, 0)),
            ]
        )
        grp_clash = CourseGroupOption(
            course_id=self.c2.id, course_code="FIS101", course_name="Física I", credits=3,
            group_number="SIS 102", available_spots=25, semester=1,
            sessions=[
                ScheduleSession(day="Miércoles", start_time=datetime.time(8, 0), end_time=datetime.time(10, 0)),
            ]
        )

        # Choca en la segunda sesión (Miércoles)
        conflicts = ScheduleEngine.check_conflicts([grp_multi, grp_clash])
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['day'], 'Miércoles')

    def test_course_without_groups_reported(self):
        """4. Asignatura sin oferta para el periodo."""
        # Creamos grupos solo para MAT101 y FIS101
        CourseGroup.objects.create(course=self.c1, course_code=self.c1.code, group_number="1", day="Lunes",
                                   start_time=datetime.time(7, 0), end_time=datetime.time(9, 0))
        # c3 no tiene CourseGroup
        proposals = ScheduleEngine.generate_recommendations([self.c1, self.c3])
        self.assertGreater(len(proposals), 0)
        self.assertIn(self.c3.name, proposals[0].missing_courses)

    def test_metrics_evaluation_wait_time_and_days(self):
        """5. Cálculo riguroso de huecos y días de clase."""
        grp1 = CourseGroupOption(
            course_id=self.c1.id, course_code="MAT101", course_name="Cálculo I", credits=4,
            group_number="1", available_spots=30, semester=1,
            sessions=[ScheduleSession(day="Lunes", start_time=datetime.time(7, 0), end_time=datetime.time(9, 0))]
        )
        grp2 = CourseGroupOption(
            course_id=self.c2.id, course_code="FIS101", course_name="Física I", credits=3,
            group_number="1", available_spots=30, semester=1,
            sessions=[ScheduleSession(day="Lunes", start_time=datetime.time(11, 0), end_time=datetime.time(13, 0))]
        )

        metrics = ScheduleEngine.evaluate_metrics([grp1, grp2])
        # Hueco de 09:00 a 11:00 = 120 minutos
        self.assertEqual(metrics.total_weekly_wait_minutes, 120)
        self.assertEqual(metrics.days_with_class, 1)
        self.assertEqual(metrics.total_class_hours, 4.0)

    def test_save_valid_schedule_and_reject_invalid(self):
        """6 y 7. Guardar horario válido e intentar guardar con cruces."""
        grp1 = CourseGroupOption(
            course_id=self.c1.id, course_code="MAT101", course_name="Cálculo I", credits=4,
            group_number="1", available_spots=30, semester=1,
            sessions=[ScheduleSession(day="Lunes", start_time=datetime.time(7, 0), end_time=datetime.time(9, 0))]
        )
        grp2 = CourseGroupOption(
            course_id=self.c2.id, course_code="FIS101", course_name="Física I", credits=3,
            group_number="1", available_spots=30, semester=1,
            sessions=[ScheduleSession(day="Lunes", start_time=datetime.time(9, 0), end_time=datetime.time(11, 0))]
        )

        valid_proposal = ScheduleEngine.validate_custom_combination([grp1, grp2])
        saved = SavedScheduleService.save_proposal(self.profile, valid_proposal, name="Mi Horario Lunes")
        self.assertTrue(saved.is_valid)
        self.assertEqual(saved.items.count(), 2)

        # Ahora con cruce
        grp_clash = CourseGroupOption(
            course_id=self.c2.id, course_code="FIS101", course_name="Física I", credits=3,
            group_number="2", available_spots=30, semester=1,
            sessions=[ScheduleSession(day="Lunes", start_time=datetime.time(8, 0), end_time=datetime.time(10, 0))]
        )
        invalid_prop = ScheduleEngine.validate_custom_combination([grp1, grp_clash])
        self.assertFalse(invalid_prop.is_valid)
        self.assertGreater(len(invalid_prop.conflicts), 0)

    def test_drift_detection_when_coursegroup_changes(self):
        """8. Detección de cambios de oferta académica."""
        cg = CourseGroup.objects.create(
            course=self.c1, course_code="MAT101", group_number="10",
            day="Lunes", start_time=datetime.time(7, 0), end_time=datetime.time(9, 0), is_active=True
        )
        grp = CourseGroupOption(
            course_id=self.c1.id, course_code="MAT101", course_name="Cálculo I", credits=4,
            group_number="10", available_spots=30, semester=1,
            sessions=[ScheduleSession(day="Lunes", start_time=datetime.time(7, 0), end_time=datetime.time(9, 0))]
        )
        prop = ScheduleEngine.validate_custom_combination([grp])
        saved_sch = SavedScheduleService.save_proposal(self.profile, prop, name="Horario Drift")

        # Antes del cambio: sin drift
        drift_before = SavedScheduleService.check_offer_changes(saved_sch)
        self.assertFalse(drift_before['has_changes'])

        # Desactivar o eliminar el grupo de la oferta vigente
        cg.is_active = False
        cg.save()

        drift_after = SavedScheduleService.check_offer_changes(saved_sch)
        self.assertTrue(drift_after['has_changes'])
        self.assertTrue(saved_sch.is_pending_review)
