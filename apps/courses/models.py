from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

class Course(models.Model):

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    credits = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(10)])
    level = models.IntegerField()
    
    program = models.ForeignKey(
        'academic.AcademicProgram',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='courses'
    )
    
    color = models.CharField(max_length=20, default='blue')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

class Prerequisite(models.Model):

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='course_prerequisites'
    )

    required_course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='required_for'
    )

    def clean(self):
        super().clean()
        if not self.course_id or not self.required_course_id:
            return

        if self.course_id == self.required_course_id:
            raise ValidationError("Una materia no puede ser prerrequisito de sí misma.")

        # Unicidad
        existing = Prerequisite.objects.filter(
            course_id=self.course_id,
            required_course_id=self.required_course_id
        )
        if self.pk:
            existing = existing.exclude(pk=self.pk)
        if existing.exists():
            raise ValidationError("Este prerrequisito ya está asignado a esta materia.")

        # Restricción de semestre/nivel: debe ser estrictamente anterior
        course = getattr(self, 'course', None) or Course.objects.filter(id=self.course_id).first()
        req_course = getattr(self, 'required_course', None) or Course.objects.filter(id=self.required_course_id).first()
        if course and req_course:
            if req_course.level >= course.level:
                raise ValidationError(
                    f"La materia '{req_course.name}' (Semestre {req_course.level}) no puede ser prerrequisito de '{course.name}' (Semestre {course.level}). Los prerrequisitos deben cursarse en un semestre estrictamente anterior."
                )

        # Ciclos: Verificar si required_course ya depende directa o indirectamente de course
        visited = set()
        queue = [self.course_id]

        while queue:
            current_id = queue.pop(0)
            if current_id == self.required_course_id:
                raise ValidationError("Ciclo detectado: la materia no puede requerir una materia que ya depende de ella.")
            
            dependents = Prerequisite.objects.filter(required_course_id=current_id).values_list('course_id', flat=True)
            for dep_id in dependents:
                if dep_id not in visited:
                    visited.add(dep_id)
                    queue.append(dep_id)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CourseGroup(models.Model):
    """
    Grupo/Sección de una materia con horario y cupos.
    Se puede importar desde CSV con el formato institucional.
    """
    DAYS_CHOICES = [
        ('Lunes', 'Lunes'),
        ('Martes', 'Martes'),
        ('Miércoles', 'Miércoles'),
        ('Jueves', 'Jueves'),
        ('Viernes', 'Viernes'),
        ('Sábado', 'Sábado'),
        ('Domingo', 'Domingo'),
    ]

    # Campos del CSV
    semester = models.IntegerField(default=1, verbose_name='Semestre')
    learning_field = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name='Campo de Aprendizaje / Núcleo Temático'
    )
    course_code = models.CharField(max_length=50, verbose_name='Código')
    course_name = models.CharField(max_length=255, blank=True, default='', verbose_name='Nombre materia')
    group_number = models.CharField(max_length=50, verbose_name='Grupo')
    available_spots = models.IntegerField(default=0, verbose_name='Cupos disponibles')
    day = models.CharField(max_length=50, blank=True, default='', verbose_name='Día')
    start_time = models.TimeField(null=True, blank=True, verbose_name='Hora inicio')
    end_time = models.TimeField(null=True, blank=True, verbose_name='Hora fin')
    classroom = models.CharField(max_length=100, blank=True, default='--', verbose_name='Salón')

    # Relación opcional con Course (se resuelve al importar si existe el código)
    course = models.ForeignKey(
        Course,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='groups'
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['semester', 'course_code', 'group_number', 'day']
        verbose_name = 'Grupo/Sección'
        verbose_name_plural = 'Grupos/Secciones'

    def __str__(self):
        return f"{self.course_code}-G{self.group_number} ({self.day} {self.start_time}-{self.end_time})"
