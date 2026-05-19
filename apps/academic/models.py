from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from apps.students.models import StudentProfile
from apps.courses.models import Course


class AcademicProgram(models.Model):
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class AcademicRecord(models.Model):

    STATUS_CHOICES = (
        ('PASSED', 'Passed'),
        ('FAILED', 'Failed'),
        ('IN_PROGRESS', 'In Progress'),
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES
    )

    grade = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(5.0)])
    
    semester_taken = models.IntegerField(default=1)

    def __str__(self):
        return f"{self.student} - {self.course}"

    def clean(self):
        super().clean()
        # Lógica de aprobación automática
        if self.grade is not None:
            if self.grade >= 3.0:
                self.status = 'PASSED'
            else:
                self.status = 'FAILED'
        
        # Validación de 3 intentos fallidos máximos
        if self.status in ['FAILED', 'IN_PROGRESS']:
            qs = AcademicRecord.objects.filter(
                student=self.student, course=self.course, status='FAILED'
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            
            failed_count = qs.count()
            if failed_count >= 3:
                raise ValidationError("El estudiante ya ha reprobado esta materia 3 veces (pérdida de calidad de estudiante).")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)