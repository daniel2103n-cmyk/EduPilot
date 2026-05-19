"""
EduPilot — Configuración principal de URLs.

Organización:
  /           → Redirección raíz
  /auth/      → authentication app (login, registro)
  /admin-ep/  → students + courses (panel administrativo)
  /student/   → students app (panel estudiante)
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect


def root_redirect(request):
    """Redirige la raíz al login."""
    return redirect('authentication:login')


urlpatterns = [
    # Django admin nativo (diferenciado con prefijo para no chocar con /admin/)
    path('django-admin/', admin.site.urls),

    # Redirección de raíz
    path('', root_redirect, name='root'),

    # ── Auth ──────────────────────────────────────────────────────────────────
    path('', include('apps.authentication.urls', namespace='authentication')),

    # ── Panel Administrador ───────────────────────────────────────────────────
    path('admin/', include('apps.students.urls.admin_urls', namespace='admin_panel')),

    # ── Panel Estudiante ──────────────────────────────────────────────────────
    path('student/', include('apps.students.urls.student_urls', namespace='student')),

    # ── Courses (gestionadas desde el panel admin) ────────────────────────────
    path('admin/courses/', include('apps.courses.urls', namespace='courses')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
