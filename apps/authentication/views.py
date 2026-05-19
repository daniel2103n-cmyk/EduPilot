"""
EduPilot — Views de Autenticación.

Responsabilidades:
  - Renderizar login / logout / registro multi-step
  - Redirección por roles (ADMIN → /admin/dashboard, STUDENT → /student/dashboard)
  - Sin lógica pesada; preparadas para integrar autenticación real en Fase 2
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib import messages
from apps.students.models import StudentProfile
from apps.academic.models import AcademicProgram

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
def login_view(request):
    """
    GET  → Muestra el formulario de login.
    POST → Autentica y redirige según rol.
    """
    # Si ya está autenticado, redirigir según su rol
    if request.user.is_authenticated:
        return _redirect_by_role(request.user)

    if request.method == 'POST':
        username_input = request.POST.get('username') or request.POST.get('email')
        password = request.POST.get('password')
        
        # Permitir login con correo
        if username_input and '@' in username_input:
            user_obj = User.objects.filter(email=username_input).first()
            if user_obj:
                username_input = user_obj.username

        user = authenticate(request, username=username_input, password=password)

        if user is not None:
            login(request, user)
            return _redirect_by_role(user)
        else:
            messages.error(request, 'Credenciales incorrectas. Intenta de nuevo.')

    context = {
        'page_title': 'Iniciar Sesión — EduPilot',
    }
    return render(request, 'auth/login.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
def logout_view(request):
    """Cierra la sesión y redirige al login."""
    logout(request)
    messages.success(request, 'Sesión cerrada correctamente.')
    return redirect('authentication:login')


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO — PASO 1 (datos personales)
# ─────────────────────────────────────────────────────────────────────────────

def register_step1_view(request):
    """
    Paso 1 del registro: captura datos básicos del estudiante.
    Los datos se guardan en session para el paso 2.
    """
    if request.user.is_authenticated:
        return _redirect_by_role(request.user)

    if request.method == 'POST':
        # Guardar datos en sesión para continuar en paso 2
        request.session['register_step1'] = {
            'first_name': request.POST.get('first_name', ''),
            'last_name':  request.POST.get('last_name', ''),
            'email':      request.POST.get('email', ''),
            'student_code': request.POST.get('student_code', ''),
        }
        return redirect('authentication:register_step2')

    context = {
        'page_title': 'Registro — Paso 1 — EduPilot',
        'step': 1,
    }
    return render(request, 'auth/registro1.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO — PASO 2 (datos académicos + contraseña)
# ─────────────────────────────────────────────────────────────────────────────

def register_step2_view(request):
    """
    Paso 2 del registro: programa académico, semestre y contraseña.
    Crea el usuario y el StudentProfile al finalizar.
    """
    if request.user.is_authenticated:
        return _redirect_by_role(request.user)

    # Verificar que paso 1 fue completado
    step1_data = request.session.get('register_step1')
    if not step1_data:
        messages.warning(request, 'Por favor completa el primer paso del registro.')
        return redirect('authentication:register_step1')

    programs = AcademicProgram.objects.filter(is_active=True)

    if request.method == 'POST':
        program_id = request.POST.get('program')
        current_semester = request.POST.get('current_semester')
        password = request.POST.get('password1')
        password_confirm = request.POST.get('password2')

        if password != password_confirm:
            messages.error(request, 'Las contraseñas no coinciden.')
            context = {
                'page_title': 'Registro — Paso 2 — EduPilot',
                'step': 2,
                'step1_data': step1_data,
                'programs': programs,
            }
            return render(request, 'auth/registro2.html', context)
        
        # Crear usuario
        try:
            user = User.objects.create_user(
                username=step1_data.get('student_code'),
                email=step1_data.get('email'),
                password=password,
                first_name=step1_data.get('first_name', ''),
                last_name=step1_data.get('last_name', ''),
                role='STUDENT'
            )
            
            # Obtener el programa
            program_obj = AcademicProgram.objects.get(id=program_id) if program_id else None

            # Crear perfil de estudiante
            StudentProfile.objects.create(
                user=user,
                program=program_obj,
                current_semester=current_semester or 1
            )
            
            request.session.pop('register_step1', None)
            messages.success(request, '¡Registro completado! Ya puedes iniciar sesión.')
            return redirect('authentication:login')
            
        except Exception as e:
            messages.error(request, 'Error al crear el usuario. Es posible que el nombre de usuario o correo ya exista.')

    context = {
        'page_title': 'Registro — Paso 2 — EduPilot',
        'step': 2,
        'step1_data': step1_data,
        'programs': programs,
    }
    return render(request, 'auth/registro2.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# UTILIDAD INTERNA
# ─────────────────────────────────────────────────────────────────────────────

def _redirect_by_role(user):
    """Redirige al dashboard correspondiente según el rol del usuario."""
    if user.is_superuser or (hasattr(user, 'role') and user.role == 'ADMIN'):
        return redirect('admin_panel:dashboard')
    return redirect('student:dashboard')
