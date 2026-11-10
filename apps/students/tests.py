from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
import json

from apps.academic.models import AcademicProgram, AcademicRecord
from apps.courses.models import Course
from apps.students.models import StudentProfile

User = get_user_model()


class StudentHistoryClearTests(TestCase):
    """Pruebas de limpieza total y limpieza semestre a semestre del historial académico."""

    def setUp(self):
        self.client = Client()
        self.program = AcademicProgram.objects.create(name="Ingeniería de Software")
        self.user = User.objects.create_user(username="test_student", password="password123")
        self.profile = StudentProfile.objects.create(user=self.user, program=self.program, current_semester=3)
        self.client.login(username="test_student", password="password123")

        # Crear cursos
        self.c1 = Course.objects.create(name="Cálculo I", code="MAT101", credits=4, level=1, program=self.program)
        self.c2 = Course.objects.create(name="Física I", code="FIS101", credits=3, level=1, program=self.program)
        self.c3 = Course.objects.create(name="Programación I", code="SIS101", credits=3, level=2, program=self.program)
        self.c4 = Course.objects.create(name="Estructuras de Datos", code="SIS102", credits=3, level=3, program=self.program)

        # Crear registros en semestres 1, 2 y 3
        AcademicRecord.objects.create(student=self.profile, course=self.c1, semester_taken=1, status='PASSED', grade=4.0)
        AcademicRecord.objects.create(student=self.profile, course=self.c2, semester_taken=1, status='PASSED', grade=3.5)
        AcademicRecord.objects.create(student=self.profile, course=self.c3, semester_taken=2, status='PASSED', grade=4.5)
        AcademicRecord.objects.create(student=self.profile, course=self.c4, semester_taken=3, status='IN_PROGRESS')

    def test_clear_semester_history_ajax(self):
        """Limpiar un semestre específico vía AJAX solo elimina registros de ese semestre."""
        url = reverse('student:historial_clear_semester')
        response = self.client.post(
            url,
            data=json.dumps({'semester': 1}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['deleted'], 2)

        # Verificar que el semestre 1 ya no tiene materias, pero los semestres 2 y 3 sí
        self.assertFalse(AcademicRecord.objects.filter(student=self.profile, semester_taken=1).exists())
        self.assertTrue(AcademicRecord.objects.filter(student=self.profile, semester_taken=2).exists())
        self.assertTrue(AcademicRecord.objects.filter(student=self.profile, semester_taken=3).exists())

    def test_clear_semester_history_post_form(self):
        """Limpiar un semestre específico vía formulario POST redirige a historial."""
        url = reverse('student:historial_clear_semester')
        response = self.client.post(url, data={'semester': 2})
        self.assertRedirects(response, reverse('student:historial'))

        # Semestre 2 debe estar vacío, semestre 1 y 3 deben permanecer
        self.assertFalse(AcademicRecord.objects.filter(student=self.profile, semester_taken=2).exists())
        self.assertEqual(AcademicRecord.objects.filter(student=self.profile, semester_taken=1).count(), 2)
        self.assertEqual(AcademicRecord.objects.filter(student=self.profile, semester_taken=3).count(), 1)

    def test_clear_all_history_ajax(self):
        """Limpiar todo el historial vía AJAX elimina absolutamente todos los registros del estudiante."""
        url = reverse('student:historial_clear_all')
        response = self.client.post(
            url,
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['deleted'], 4)

        # No debe quedar ningún registro
        self.assertEqual(AcademicRecord.objects.filter(student=self.profile).count(), 0)

    def test_clear_all_history_post_form(self):
        """Limpiar todo el historial vía POST tradicional redirige a historial."""
        url = reverse('student:historial_clear_all')
        response = self.client.post(url)
        self.assertRedirects(response, reverse('student:historial'))
        self.assertEqual(AcademicRecord.objects.filter(student=self.profile).count(), 0)


class StudentHistoryFailedAndRetakeTests(TestCase):
    """Pruebas de preservación y visualización de materias reprobadas y repeticiones."""

    def setUp(self):
        self.client = Client()
        self.program = AcademicProgram.objects.create(name="Ingeniería de Software")
        self.user = User.objects.create_user(username="student_retake", password="password123")
        self.profile = StudentProfile.objects.create(user=self.user, program=self.program, current_semester=2)
        self.client.login(username="student_retake", password="password123")

        self.c1 = Course.objects.create(name="Cálculo I", code="MAT101", credits=4, level=1, program=self.program)

    def test_retake_course_preserves_both_failed_and_passed_records(self):
        """Si un estudiante reprueba en semestre 1 y aprueba en semestre 2, ambos registros existen."""
        # 1. Registrar reprobada en Semestre 1
        AcademicRecord.objects.create(
            student=self.profile, course=self.c1, semester_taken=1, status='FAILED', grade=2.0
        )

        # 2. Registrar aprobada en Semestre 2 vía bulk_save
        url = reverse('student:historial_bulk_save')
        payload = {
            'semester': 2,
            'records': [
                {'course_id': self.c1.id, 'status': 'PASSED', 'grade': 4.2}
            ]
        }
        response = self.client.post(
            url, data=json.dumps(payload), content_type='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)

        # Verificar que existen 2 registros distintos en la base de datos para la misma materia
        c1_records = AcademicRecord.objects.filter(student=self.profile, course=self.c1).order_by('semester_taken')
        self.assertEqual(c1_records.count(), 2)

        sem1_rec = c1_records[0]
        self.assertEqual(sem1_rec.semester_taken, 1)
        self.assertEqual(sem1_rec.status, 'FAILED')
        self.assertEqual(sem1_rec.grade, 2.0)

        sem2_rec = c1_records[1]
        self.assertEqual(sem2_rec.semester_taken, 2)
        self.assertEqual(sem2_rec.status, 'PASSED')
        self.assertEqual(sem2_rec.grade, 4.2)

    def test_historial_view_marks_retaken_courses(self):
        """La vista de historial calcula y marca que la reprobada fue superada posteriormente."""
        AcademicRecord.objects.create(
            student=self.profile, course=self.c1, semester_taken=1, status='FAILED', grade=2.2
        )
        AcademicRecord.objects.create(
            student=self.profile, course=self.c1, semester_taken=2, status='PASSED', grade=3.8
        )

        response = self.client.get(reverse('student:historial'))
        self.assertEqual(response.status_code, 200)

        sorted_sems = response.context['sorted_semesters']
        self.assertEqual(len(sorted_sems), 2)

        # Semestre 1 debe contener el registro fallido enriquecido
        sem1_records = sorted_sems[0]['records']
        self.assertEqual(len(sem1_records), 1)
        self.assertTrue(getattr(sem1_records[0], 'was_retaken_and_passed', False))
        self.assertEqual(sem1_records[0].retaken_in_semester, 2)

        # Semestre 2 debe contener el registro aprobado como repitencia exitosa
        sem2_records = sorted_sems[1]['records']
        self.assertEqual(len(sem2_records), 1)
        self.assertTrue(getattr(sem2_records[0], 'is_retake_success', False))

