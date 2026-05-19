from django.db import transaction
from apps.academic.models import AcademicRecord
from apps.courses.models import Course

class AcademicService:

    @classmethod
    def autofill_academic_records(cls, profile):
        """
        Autocompleta el historial del estudiante simulando los semestres anteriores.
        Reglas:
        - Máximo 18 créditos por semestre.
        - Se respetan los prerrequisitos.
        - Semestres < current_semester -> PASSED con nota 3.0.
        - Semestre == current_semester -> IN_PROGRESS con nota 0.0.
        No toca las materias que ya tengan un registro (para no borrar historial manual).
        """
        if not profile or not profile.program_id:
            return 0

        # Obtener ids de cursos que ya tienen algún registro
        existing_records = AcademicRecord.objects.filter(student=profile)
        taken_course_ids = set(existing_records.values_list('course_id', flat=True))

        # Obtenemos todos los cursos del programa
        all_courses = list(
            Course.objects.filter(program=profile.program, is_active=True)
            .prefetch_related('course_prerequisites')
            .order_by('level', '-credits', 'name')
        )

        passed_course_ids = set(
            existing_records.filter(status='PASSED').values_list('course_id', flat=True)
        )

        records_created = 0

        with transaction.atomic():
            # Simulamos desde el semestre 1 hasta el semestre actual del estudiante
            for sim_semester in range(1, profile.current_semester + 1):
                credits_in_semester = 0
                
                # Buscar qué cursos se pueden ver en este semestre simulado
                available_for_sim = []
                for course in all_courses:
                    if course.id in taken_course_ids:
                        continue # Ya tiene registro, lo saltamos
                    
                    # Checar prerrequisitos
                    prereqs = course.course_prerequisites.all()
                    prereqs_met = all(p.required_course_id in passed_course_ids for p in prereqs)
                    
                    if prereqs_met and course.level <= sim_semester:
                        available_for_sim.append(course)

                # Tomar materias hasta llegar a 18 créditos
                courses_to_take = []
                for course in available_for_sim:
                    if credits_in_semester + course.credits <= 18:
                        courses_to_take.append(course)
                        credits_in_semester += course.credits
                        taken_course_ids.add(course.id) # Marcar como tomado para que no vuelva a salir
                
                # Crear los registros
                for course in courses_to_take:
                    if sim_semester < profile.current_semester:
                        # Pasó la materia
                        AcademicRecord.objects.create(
                            student=profile,
                            course=course,
                            status='PASSED',
                            grade=3.0,
                            semester_taken=sim_semester
                        )
                        passed_course_ids.add(course.id)
                    else:
                        # Está en el semestre actual, en curso
                        AcademicRecord.objects.create(
                            student=profile,
                            course=course,
                            status='IN_PROGRESS',
                            grade=None,
                            semester_taken=sim_semester
                        )
                    records_created += 1

        return records_created
