"""
EduPilot — URLs de Cursos.

Rutas bajo /admin/courses/:
  (vacío por ahora — la gestión de cursos se hace desde admin_views)
"""

from django.urls import path
from . import views

app_name = 'courses'

urlpatterns = [
    # Placeholder — CRUD de cursos se implementa en Fase 2
]
