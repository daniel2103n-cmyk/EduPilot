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

        # Ciclos: Verificar si required_course ya depende de course
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