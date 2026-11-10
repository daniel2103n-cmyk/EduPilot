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
    path('dashboard/',        student_views.student_dashboard_view,      name='dashboard'),
    path('historial/',        student_views.student_historial_view,      name='historial'),
    path('historial/save/',       student_views.save_academic_record_view,       name='historial_save'),
    path('historial/bulk-save/',  student_views.bulk_save_academic_records_view, name='historial_bulk_save'),
    path('historial/delete/',     student_views.delete_academic_record_view,     name='historial_delete'),
    path('courses/',          student_views.student_courses_view,        name='courses'),
    
    # Rutas Académicas
    path('routes/',           student_views.student_routes_view,         name='routes'),
    path('routes/save/',      student_views.save_route_view,             name='routes_save'),
    path('routes/set-favorite/<int:route_id>/', student_views.set_favorite_route_view, name='routes_set_favorite'),
    path('routes/delete/<int:route_id>/',       student_views.delete_route_view,       name='routes_delete'),
    path('routes/ai-explanation/',              student_views.route_ai_explanation_view, name='routes_ai_explanation'),

    # Horarios y Matrícula
    path('horarios/',         student_views.student_horarios_view,       name='horarios'),
    path('horarios/validate/', student_views.validate_schedule_view,     name='horarios_validate'),
    path('horarios/save/',     student_views.save_schedule_view,         name='horarios_save'),
    path('horarios/delete/<int:schedule_id>/', student_views.delete_schedule_view, name='horarios_delete'),
    path('horarios/ai-explanation/',           student_views.schedule_ai_explanation_view, name='horarios_ai_explanation'),

    # Planes Guardados
    path('guardados/',        student_views.student_guardados_view,      name='guardados'),
    path('courses/autofill/', student_views.autofill_records_view,       name='courses_autofill'),
    path('courses/update/',   student_views.update_academic_record_view, name='courses_update'),

    # Limpieza de historial
    path('historial/clear-all/',      student_views.clear_all_history_view,      name='historial_clear_all'),
    path('historial/clear-semester/', student_views.clear_semester_history_view, name='historial_clear_semester'),
]

