from django.db import models
from django.conf import settings
from apps.students.models import StudentProfile
from apps.academic.models import AcademicProgram
from apps.courses.models import Course, CourseGroup


class SavedRoute(models.Model):
    """
    Ruta académica guardada por el estudiante.
    Conserva una instantánea coherente de la planificación elegida.
    """
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='saved_routes',
        verbose_name='Estudiante'
    )
    program = models.ForeignKey(
        AcademicProgram,
        on_delete=models.CASCADE,
        related_name='saved_routes',
        verbose_name='Programa'
    )
    name = models.CharField(max_length=200, verbose_name='Nombre del Plan')
    strategy_key = models.CharField(max_length=50, verbose_name='Estrategia')
    strategy_label = models.CharField(max_length=100, default='', blank=True, verbose_name='Etiqueta de Estrategia')
    is_favorite = models.BooleanField(default=False, verbose_name='Ruta preferida')
    
    # Métricas persistidas
    estimated_semesters = models.IntegerField(default=0, verbose_name='Semestres estimados')
    total_credits = models.IntegerField(default=0, verbose_name='Total créditos')
    total_courses = models.IntegerField(default=0, verbose_name='Total materias')
    is_within_ideal_limit = models.BooleanField(default=True, verbose_name='Dentro del margen ideal (<=10 sem)')
    over_limit_semesters = models.IntegerField(default=0, verbose_name='Semestres sobre margen ideal')
    
    academic_period = models.CharField(max_length=20, default='2025-1', verbose_name='Periodo de creación')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadatos y advertencias')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_favorite', '-updated_at']
        verbose_name = 'Ruta Guardada'
        verbose_name_plural = 'Rutas Guardadas'

    def __str__(self):
        return f"{self.name} ({self.student.user.username})"

    def mark_as_favorite(self):
        """Marca esta ruta como favorita y desmarca las demás del estudiante."""
        SavedRoute.objects.filter(student=self.student).exclude(pk=self.pk).update(is_favorite=False)
        self.is_favorite = True
        self.save(update_fields=['is_favorite', 'updated_at'])


class SavedRouteSemester(models.Model):
    """Semestre proyectado dentro de una ruta guardada."""
    route = models.ForeignKey(
        SavedRoute,
        on_delete=models.CASCADE,
        related_name='semesters',
        verbose_name='Ruta'
    )
    semester_number = models.IntegerField(verbose_name='Número de Semestre Proyectado')
    total_credits = models.IntegerField(default=0, verbose_name='Créditos del Semestre')

    class Meta:
        ordering = ['semester_number']
        verbose_name = 'Semestre de Ruta'
        verbose_name_plural = 'Semestres de Rutas'

    def __str__(self):
        return f"{self.route.name} - Semestre {self.semester_number}"


class SavedRouteCourse(models.Model):
    """
    Asignatura planificada en un semestre de la ruta.
    Guarda referencias a Course y snapshots de código, nombre y créditos.
    """
    semester = models.ForeignKey(
        SavedRouteSemester,
        on_delete=models.CASCADE,
        related_name='courses',
        verbose_name='Semestre'
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='saved_in_routes',
        verbose_name='Materia'
    )
    course_code_snapshot = models.CharField(max_length=50, verbose_name='Código histórico')
    course_name_snapshot = models.CharField(max_length=255, verbose_name='Nombre histórico')
    credits_snapshot = models.IntegerField(default=0, verbose_name='Créditos históricos')
    level_snapshot = models.IntegerField(default=1, verbose_name='Nivel histórico')

    class Meta:
        ordering = ['level_snapshot', 'course_name_snapshot']
        verbose_name = 'Materia de Ruta'
        verbose_name_plural = 'Materias de Rutas'

    def __str__(self):
        return f"{self.course_code_snapshot} ({self.semester})"


class SavedSchedule(models.Model):
    """
    Horario guardado por el estudiante para el semestre académico vigente.
    Asociado opcionalmente a la ruta académica de la cual proviene.
    """
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='saved_schedules',
        verbose_name='Estudiante'
    )
    saved_route = models.ForeignKey(
        SavedRoute,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='schedules',
        verbose_name='Ruta de origen'
    )
    name = models.CharField(max_length=200, default='Mi Horario Semestral', verbose_name='Nombre del horario')
    academic_period = models.CharField(max_length=20, default='2025-1', verbose_name='Periodo académico')
    is_valid = models.BooleanField(default=True, verbose_name='Horario validado sin cruces')
    is_pending_review = models.BooleanField(default=False, verbose_name='Pendiente de revisión por cambio de oferta')
    
    metrics = models.JSONField(default=dict, blank=True, verbose_name='Métricas de calidad de horario')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Horario Guardado'
        verbose_name_plural = 'Horarios Guardados'

    def __str__(self):
        return f"{self.name} - {self.student.user.username} ({self.academic_period})"


class SavedScheduleItem(models.Model):
    """Grupo o sección asignada a una materia dentro del horario guardado."""
    schedule = models.ForeignKey(
        SavedSchedule,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Horario'
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        verbose_name='Materia'
    )
    course_code_snapshot = models.CharField(max_length=50)
    course_name_snapshot = models.CharField(max_length=255)
    group_number = models.CharField(max_length=50, verbose_name='Grupo seleccionado')
    credits_snapshot = models.IntegerField(default=0)
    
    # Lista de sesiones [{day, start_time, end_time, classroom}]
    sessions_snapshot = models.JSONField(default=list, blank=True, verbose_name='Sesiones semanales')

    class Meta:
        ordering = ['course_name_snapshot']
        verbose_name = 'Elemento de Horario'
        verbose_name_plural = 'Elementos de Horario'

    def __str__(self):
        return f"{self.course_code_snapshot}-G{self.group_number} en {self.schedule.name}"
