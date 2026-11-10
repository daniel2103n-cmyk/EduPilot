"""
EduPilot — Pruebas Automatizadas del Motor de Rutas y Persistencia
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from apps.academic.models import AcademicProgram, AcademicRecord
from apps.courses.models import Course, Prerequisite
from apps.students.models import StudentProfile
from apps.routes.models import SavedRoute, SavedRouteSemester, SavedRouteCourse
from apps.routes.services.saved_route_service import SavedRouteService
from services.route_generator import RouteGeneratorService, Strategy, RouteResult

User = get_user_model()


class RouteEngineAcademicTests(TestCase):
    """Pruebas del motor algorítmico de rutas académicas."""

    def setUp(self):
        self.program = AcademicProgram.objects.create(name="Ingeniería de Sistemas y Computación")
        self.user = User.objects.create_user(username="student_test", password="testpassword123")
        self.profile = StudentProfile.objects.create(user=self.user, program=self.program, current_semester=1)

        # Crear malla básica de prueba: 4 niveles
        # Nivel 1
        self.c1 = Course.objects.create(name="Cálculo I", code="MAT101", credits=4, level=1, program=self.program)
        self.c2 = Course.objects.create(name="Álgebra Lineal", code="MAT102", credits=3, level=1, program=self.program)
        self.c3 = Course.objects.create(name="Intro a la Programación", code="SIS101", credits=3, level=1, program=self.program)

        # Nivel 2
        self.c4 = Course.objects.create(name="Cálculo II", code="MAT201", credits=4, level=2, program=self.program)
        self.c5 = Course.objects.create(name="Programación Orientada a Objetos", code="SIS201", credits=3, level=2, program=self.program)

        # Nivel 3
        self.c6 = Course.objects.create(name="Estructuras de Datos", code="SIS301", credits=4, level=3, program=self.program)

        # Nivel 4
        self.c7 = Course.objects.create(name="Bases de Datos", code="SIS401", credits=3, level=4, program=self.program)

        # Prerrequisitos:
        # MAT201 requiere MAT101
        Prerequisite.objects.create(course=self.c4, required_course=self.c1)
        # SIS201 requiere SIS101
        Prerequisite.objects.create(course=self.c5, required_course=self.c3)
        # SIS301 requiere SIS201
        Prerequisite.objects.create(course=self.c6, required_course=self.c5)
        # SIS401 requiere SIS301
        Prerequisite.objects.create(course=self.c7, required_course=self.c6)

    def test_student_without_pending_courses(self):
        """1. Estudiante que ya aprobó todas las materias del programa."""
        courses = [self.c1, self.c2, self.c3, self.c4, self.c5, self.c6, self.c7]
        for c in courses:
            AcademicRecord.objects.create(student=self.profile, course=c, status='PASSED', grade=4.5)

        route = RouteGeneratorService.generate(self.profile, Strategy.BALANCED)
        self.assertTrue(route.is_empty)
        self.assertIn("Has completado todas las asignaturas", route.error)

    def test_student_with_single_pending_course(self):
        """2. Estudiante con una sola materia pendiente."""
        # Aprobó todo excepto SIS401
        for c in [self.c1, self.c2, self.c3, self.c4, self.c5, self.c6]:
            AcademicRecord.objects.create(student=self.profile, course=c, status='PASSED', grade=4.0)

        route = RouteGeneratorService.generate(self.profile, Strategy.BALANCED)
        self.assertFalse(route.is_empty)
        self.assertEqual(route.total_courses, 1)
        self.assertEqual(route.estimated_semesters, 1)
        self.assertEqual(route.semesters[0].courses[0].id, self.c7.id)

    def test_course_with_prerequisites_sequencing(self):
        """3 y 4. Asignatura con prerrequisitos y cadena secuencial respetada."""
        # Estudiante nuevo sin nada aprobado
        route = RouteGeneratorService.generate(self.profile, Strategy.FAST_TRACK)
        self.assertFalse(route.is_empty)

        # Verificar que Cálculo II no esté en el Semestre 1 (debe estar en Semestre 2 o después)
        sem1_course_ids = [c.id for c in route.semesters[0].courses]
        self.assertIn(self.c1.id, sem1_course_ids)
        self.assertNotIn(self.c4.id, sem1_course_ids)

        # Verificar que Estructuras de Datos (SIS301) aparezca después de POO (SIS201)
        sem_poo = next(s.number for s in route.semesters if any(c.id == self.c5.id for c in s.courses))
        sem_ed = next(s.number for s in route.semesters if any(c.id == self.c6.id for c in s.courses))
        self.assertGreater(sem_ed, sem_poo)

    def test_passed_courses_not_scheduled_again(self):
        """5. Materias aprobadas no deben volver a planificarse."""
        AcademicRecord.objects.create(student=self.profile, course=self.c1, status='PASSED', grade=3.8)
        AcademicRecord.objects.create(student=self.profile, course=self.c2, status='PASSED', grade=4.2)

        route = RouteGeneratorService.generate(self.profile, Strategy.BALANCED)
        all_scheduled_ids = [c.id for s in route.semesters for c in s.courses]

        self.assertNotIn(self.c1.id, all_scheduled_ids)
        self.assertNotIn(self.c2.id, all_scheduled_ids)
        self.assertEqual(route.passed_count, 2)

    def test_route_within_ideal_10_semesters(self):
        """6. Ruta que termina dentro del margen ideal de 10 semestres."""
        route = RouteGeneratorService.generate(self.profile, Strategy.FAST_TRACK)
        self.assertTrue(route.is_within_ideal_limit)
        self.assertLessEqual(route.estimated_semesters, 10)
        self.assertEqual(route.over_limit_semesters, 0)

    def test_route_over_ideal_semesters(self):
        """7. Ruta que supera el margen ideal pero sigue siendo válida."""
        # Creamos una cadena de 12 niveles con 1 materia por nivel
        prev = self.c7
        chain = []
        for i in range(5, 15):
            c = Course.objects.create(name=f"Materia Nivel {i}", code=f"MAT{i}01", credits=3, level=i, program=self.program)
            # Prereq manual sin validación de clean para testear el algoritmo de ruta
            p = Prerequisite(course=c, required_course=prev)
            p.save_base()
            prev = c
            chain.append(c)

        route = RouteGeneratorService.generate(self.profile, Strategy.LIGHT)
        self.assertFalse(route.is_within_ideal_limit)
        self.assertGreater(route.estimated_semesters, 10)
        self.assertGreater(route.over_limit_semesters, 0)
        self.assertTrue(len(route.over_limit_factors) > 0)

    def test_cycle_detection(self):
        """9. Detección de ciclos inválidos en el grafo de prerrequisitos."""
        # Creamos un ciclo circular c1 -> c2 -> c1 saltando validaciones de modelo
        p_cycle = Prerequisite(course=self.c1, required_course=self.c4)
        p_cycle.save_base()

        route = RouteGeneratorService.generate(self.profile, Strategy.BALANCED)
        self.assertTrue(route.is_empty)
        self.assertIn("ciclo", route.error.lower())

    def test_multi_alternatives_generation_and_deduplication(self):
        """10 y 11. Generación de alternativas diferentes y deduplicación."""
        alts = RouteGeneratorService.generate_alternatives(self.profile)
        self.assertGreaterEqual(len(alts), 1)
        self.assertLessEqual(len(alts), 3)

        # Comprobar que no hay duplicados exactos en la lista
        signatures = [alt.signature for alt in alts]
        self.assertEqual(len(signatures), len(set(signatures)))


class RoutePersistenceAndSecurityTests(TestCase):
    """Pruebas de persistencia, snapshots históricos y aislamiento de seguridad."""

    def setUp(self):
        self.program = AcademicProgram.objects.create(name="Ingeniería de Sistemas")
        self.user1 = User.objects.create_user(username="student_1", password="password1")
        self.profile1 = StudentProfile.objects.create(user=self.user1, program=self.program)

        self.user2 = User.objects.create_user(username="student_2", password="password2")
        self.profile2 = StudentProfile.objects.create(user=self.user2, program=self.program)

        self.c1 = Course.objects.create(name="Cálculo I", code="MAT101", credits=4, level=1, program=self.program)
        self.c2 = Course.objects.create(name="Física I", code="FIS101", credits=3, level=1, program=self.program)

    def test_save_route_creates_snapshot(self):
        """Verifica guardado de ruta con snapshots de código, nombre y créditos."""
        route_result = RouteGeneratorService.generate(self.profile1, Strategy.BALANCED)
        saved = SavedRouteService.save_route(self.profile1, route_result, name="Mi Plan de Graduación", is_favorite=True)

        self.assertEqual(saved.student, self.profile1)
        self.assertEqual(saved.name, "Mi Plan de Graduación")
        self.assertTrue(saved.is_favorite)
        self.assertGreater(saved.semesters.count(), 0)

        first_course_snap = saved.semesters.first().courses.first()
        self.assertEqual(first_course_snap.course_code_snapshot, first_course_snap.course.code)
        self.assertEqual(first_course_snap.course_name_snapshot, first_course_snap.course.name)

        # Si el Course original cambia de nombre o créditos en el futuro, el snapshot debe preservarse
        original_course = first_course_snap.course
        original_course.name = "Cálculo Diferencial Avanzado"
        original_course.save()

        first_course_snap.refresh_from_db()
        self.assertEqual(first_course_snap.course_name_snapshot, "Cálculo I")

    def test_security_isolation_between_students(self):
        """Un estudiante no puede consultar ni modificar ni eliminar rutas de otro."""
        route_result = RouteGeneratorService.generate(self.profile1, Strategy.BALANCED)
        saved = SavedRouteService.save_route(self.profile1, route_result, name="Ruta Estudiante 1")

        # El estudiante 2 intenta acceder a la ruta del estudiante 1
        with self.assertRaises(PermissionDenied):
            SavedRouteService.get_route_for_student(self.profile2, saved.id)

        # El estudiante 2 intenta eliminar la ruta del estudiante 1
        with self.assertRaises(PermissionDenied):
            SavedRouteService.delete_route(self.profile2, saved.id)

    def test_set_favorite_toggles_others(self):
        """Al marcar una ruta como favorita, las demás del mismo estudiante se desmarcan."""
        rr = RouteGeneratorService.generate(self.profile1, Strategy.BALANCED)
        r1 = SavedRouteService.save_route(self.profile1, rr, name="Ruta 1", is_favorite=True)
        r2 = SavedRouteService.save_route(self.profile1, rr, name="Ruta 2", is_favorite=False)

        SavedRouteService.set_favorite(self.profile1, r2.id)

        r1.refresh_from_db()
        r2.refresh_from_db()

        self.assertFalse(r1.is_favorite)
        self.assertTrue(r2.is_favorite)
