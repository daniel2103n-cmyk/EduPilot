from django.db import models
from django.conf import settings


class StudentProfile(models.Model):

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    program = models.ForeignKey(
        'academic.AcademicProgram',
        on_delete=models.SET_NULL,
        null=True, blank=True
    )

    current_semester = models.IntegerField(default=1)

    def __str__(self):
        return self.user.username