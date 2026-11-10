"""
EduPilot — CourseSyncService
============================
Servicio de sincronización y reconciliación automática entre asignaturas (Course)
y la oferta de horarios/secciones (CourseGroup).

Garantiza consistencia bidireccional:
  - Ningún grupo/horario queda huérfano sin materia asociada.
  - Al importar horarios desde CSV, se crean automáticamente las materias en el plan de estudios.
"""

from __future__ import annotations
import logging
from django.db import transaction
from apps.academic.models import AcademicProgram
from apps.courses.models import Course, CourseGroup

logger = logging.getLogger(__name__)


class CourseSyncService:
    """
    Sincroniza y reconcilia asignaturas a partir de los grupos y horarios importados.
    """

    @classmethod
    @transaction.atomic
    def sync_unlinked_groups(cls, default_program: AcademicProgram | None = None) -> dict:
        """
        Detecta todos los CourseGroup que no tienen Course asociado y:
          1. Intenta vincularlos con un Course existente por código o nombre (limpiando espacios).
          2. Si la materia no existe en el catálogo, la crea automáticamente en el programa académico.
        """
        if not default_program:
            default_program = AcademicProgram.objects.filter(is_active=True).first()

        unlinked_groups = CourseGroup.objects.filter(course__isnull=True)
        total_unlinked_start = unlinked_groups.count()

        courses_created_count = 0
        groups_linked_count = 0
        created_courses_list = []

        # Mapa de materias existentes
        course_map_code = {c.code.strip().upper(): c for c in Course.objects.all()}
        course_map_name = {c.name.strip().upper(): c for c in Course.objects.all()}

        for group in unlinked_groups:
            code_clean = (group.course_code or '').strip()
            name_clean = (group.learning_field or group.course_name or '').strip()
            sem = group.semester or 1

            if not code_clean:
                continue

            matched_course = course_map_code.get(code_clean.upper()) or course_map_name.get(name_clean.upper())

            if not matched_course:
                # Estimar créditos según el tipo de materia
                name_upper = name_clean.upper()
                if any(w in name_upper for w in ['CÁLCULO', 'CALCULO', 'FÍSICA', 'FISICA', 'ÁLGEBRA', 'ALGEBRA', 'ESTRUCTURAS']):
                    credits_val = 4
                elif any(w in name_upper for w in ['DIAGNOSTICO', 'NIVELATORIO', 'ELECTIVA']):
                    credits_val = 2
                else:
                    credits_val = 3

                matched_course = Course.objects.create(
                    code=code_clean,
                    name=name_clean or f"Asignatura {code_clean}",
                    level=sem,
                    credits=credits_val,
                    program=default_program,
                    is_active=True
                )
                course_map_code[code_clean.upper()] = matched_course
                course_map_name[name_clean.upper()] = matched_course
                courses_created_count += 1
                created_courses_list.append(matched_course)
                logger.info("[CourseSyncService] Creada materia automática: %s (%s, Sem %d)", matched_course.name, matched_course.code, matched_course.level)

            group.course = matched_course
            if not group.course_name:
                group.course_name = matched_course.name
            group.save(update_fields=['course', 'course_name'])
            groups_linked_count += 1

        return {
            'unlinked_initial': total_unlinked_start,
            'courses_created': courses_created_count,
            'groups_linked': groups_linked_count,
            'created_courses': created_courses_list,
        }

    @classmethod
    def get_or_create_course_for_import(
        cls,
        code: str,
        name: str,
        semester: int = 1,
        program: AcademicProgram | None = None
    ) -> tuple[Course, bool]:
        """
        Usado durante la importación línea a línea de CSV:
        Garantiza que la materia exista en el catálogo de Course.
        """
        code_clean = code.strip()
        name_clean = name.strip()

        matched = Course.objects.filter(code__iexact=code_clean).first()
        if not matched and name_clean:
            matched = Course.objects.filter(name__iexact=name_clean).first()

        if matched:
            return matched, False

        if not program:
            program = AcademicProgram.objects.filter(is_active=True).first()

        name_upper = name_clean.upper()
        if any(w in name_upper for w in ['CÁLCULO', 'CALCULO', 'FÍSICA', 'FISICA', 'ÁLGEBRA', 'ALGEBRA', 'ESTRUCTURAS']):
            credits_val = 4
        elif any(w in name_upper for w in ['DIAGNOSTICO', 'NIVELATORIO', 'ELECTIVA']):
            credits_val = 2
        else:
            credits_val = 3

        new_course = Course.objects.create(
            code=code_clean,
            name=name_clean or f"Materia {code_clean}",
            level=semester or 1,
            credits=credits_val,
            program=program,
            is_active=True
        )
        return new_course, True
