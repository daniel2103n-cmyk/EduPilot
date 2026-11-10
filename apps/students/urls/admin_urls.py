"""
EduPilot — URLs del Panel Administrador.

Rutas bajo /admin/:
  /admin/dashboard/    → admin_dashboard_view
  /admin/students/     → admin_students_view
  /admin/courses/      → admin_courses_view  (manejado por courses app)
"""

from django.urls import path
from apps.students.views import admin_views

app_name = 'admin_panel'

urlpatterns = [
    path('dashboard/',                  admin_views.admin_dashboard_view,      name='dashboard'),
    path('students/',                   admin_views.admin_students_view,       name='students'),
    path('students/<int:student_id>/',  admin_views.admin_student_detail_view, name='student_detail'),
    path('courses/',                    admin_views.admin_courses_view,        name='courses'),
    path('programs/',                   admin_views.admin_programs_view,       name='programs'),
    path('schedules/',                  admin_views.admin_schedules_view,      name='schedules'),
]
