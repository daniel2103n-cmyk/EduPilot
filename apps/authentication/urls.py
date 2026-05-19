"""
EduPilot — URLs de Autenticación.

Rutas:
  /login/              → login_view
  /logout/             → logout_view
  /register/step-1/    → register_step1_view
  /register/step-2/    → register_step2_view
"""

from django.urls import path
from . import views

app_name = 'authentication'

urlpatterns = [
    path('login/',              views.login_view,          name='login'),
    path('logout/',             views.logout_view,         name='logout'),
    path('register/step-1/',    views.register_step1_view, name='register_step1'),
    path('register/step-2/',    views.register_step2_view, name='register_step2'),
]
