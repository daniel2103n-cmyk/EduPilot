"""
EduPilot — URLs del Panel Estudiante.

Rutas bajo /student/:
  /student/dashboard/  → student_dashboard_view
  /student/courses/    → student_courses_view
  /student/routes/     → student_routes_view
"""

from django.urls import path
from apps.students.views import student_views

app_name = 'student'

urlpatterns = [
    path('dashboard/',  student_views.student_dashboard_view,  name='dashboard'),
    path('courses/',    student_views.student_courses_view,    name='courses'),
    path('routes/',     student_views.student_routes_view,     name='routes'),
    path('courses/autofill/', student_views.autofill_records_view, name='courses_autofill'),
    path('courses/update/', student_views.update_academic_record_view, name='courses_update'),
]
