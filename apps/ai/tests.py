"""
EduPilot — Pruebas Automatizadas de los Servicios de IA (Rutas y Horarios)
"""

import datetime
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.academic.models import AcademicProgram
from apps.courses.models import Course
from apps.students.models import StudentProfile
from apps.ai.services.ai_service import ai_service
from services.route_generator import RouteGeneratorService, Strategy
from services.schedule_engine import (
    ScheduleEngine, ScheduleSession, CourseGroupOption
)

User = get_user_model()


class AIServiceTests(TestCase):
    """Pruebas de los servicios de IA y su resiliencia."""

    def setUp(self):
        self.program = AcademicProgram.objects.create(name="Ingeniería Industrial")
        self.user = User.objects.create_user(username="student_ai", password="password123")
        self.profile = StudentProfile.objects.create(user=self.user, program=self.program, current_semester=2)

        self.c1 = Course.objects.create(name="Cálculo Diferencial", code="MAT101", credits=4, level=1, program=self.program)
        self.c2 = Course.objects.create(name="Física Mecánica", code="FIS101", credits=3, level=1, program=self.program)

    def test_explain_route_returns_7_sections_fallback(self):
        """1. explain_route devuelve explicación estructurada en 7 secciones ante fallback."""
        route = RouteGeneratorService.generate(self.profile, Strategy.BALANCED)
        # Forzamos desconexión simulando caída de requests
        with patch('requests.post', side_effect=Exception("Connection refused")):
            explanation = ai_service.explain_route(self.profile, route)

        self.assertIsInstance(explanation, str)
        self.assertIn("1. **Resumen de la estrategia**", explanation)
        self.assertIn("2. **Explicación de la trayectoria**", explanation)
        self.assertIn("3. **Análisis de los semestres**", explanation)
        self.assertIn("4. **Materias críticas y dependencias**", explanation)
        self.assertIn("5. **Ventajas y desventajas**", explanation)
        self.assertIn("6. **Riesgos o restricciones**", explanation)
        self.assertIn("7. **Recomendación final**", explanation)

    def test_explain_schedule_returns_metrics_in_explanation(self):
        """2. explain_schedule utiliza y refleja las métricas reales del horario."""
        grp = CourseGroupOption(
            course_id=self.c1.id, course_code="MAT101", course_name="Cálculo Diferencial", credits=4,
            group_number="1", available_spots=30, semester=1,
            sessions=[
                ScheduleSession(day="Lunes", start_time=datetime.time(7, 0), end_time=datetime.time(9, 0)),
                ScheduleSession(day="Miércoles", start_time=datetime.time(7, 0), end_time=datetime.time(9, 0)),
            ]
        )
        proposal = ScheduleEngine.validate_custom_combination([grp])

        with patch('requests.post', side_effect=Exception("Timeout")):
            explanation = ai_service.explain_schedule(self.profile, proposal)

        self.assertIsInstance(explanation, str)
        self.assertIn("1. **Resumen de la distribución semanal**", explanation)
        self.assertIn("4.0 horas", explanation)
        self.assertIn("2 días", explanation)
        self.assertIn("Cálculo Diferencial", explanation)

    def test_ai_failure_does_not_affect_route_or_schedule_validity(self):
        """3. El fallo de IA nunca altera la validez del cálculo algorítmico."""
        route = RouteGeneratorService.generate(self.profile, Strategy.BALANCED)
        self.assertFalse(route.is_empty)

        # Si la IA falla, la ruta sigue completamente funcional
        with patch('requests.post', side_effect=Exception("API Error 500")):
            explanation = ai_service.explain_route(self.profile, route)

        self.assertTrue(len(explanation) > 0)
        self.assertFalse(route.is_empty)
        self.assertEqual(route.estimated_semesters, 1)
