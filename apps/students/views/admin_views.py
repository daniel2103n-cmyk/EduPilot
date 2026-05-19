"""
EduPilot — Views del Panel Administrador.

Responsabilidades:
  - Renderizar vistas del panel de administración
  - Pasar contexto básico (placeholder para Fase 2)
  - Verificar autenticación y rol ADMIN
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.contrib.auth import get_user_model
from apps.students.models import StudentProfile
from apps.academic.models import AcademicProgram
from apps.courses.models import Course

User = get_user_model()


def is_admin(user):
    return user.is_superuser or (hasattr(user, 'role') and user.role == 'ADMIN')


def _require_admin(request):
    """
    Verifica que el usuario sea ADMIN o superusuario.
    Retorna None si OK, o una respuesta de redirect si no.
    """
    if not request.user.is_authenticated:
        return redirect('authentication:login')
    if not (request.user.is_superuser or (hasattr(request.user, 'role') and request.user.role == 'ADMIN')):
        messages.error(request, 'No tienes permisos para acceder al panel de administración.')
        return redirect('student:dashboard')
    return None


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD ADMIN
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@user_passes_test(is_admin)
def admin_dashboard_view(request):
    """
    Panel principal del administrador.
    Contexto preparado para estadísticas (Fase 2 llenará con datos reales).
    """
    guard = _require_admin(request)
    if guard:
        return guard

    stats = {
        'total_students': StudentProfile.objects.count(),
        'total_courses': Course.objects.count(),
        'total_programs': AcademicProgram.objects.filter(is_active=True).count(),
        'total_prerequisites': 0,
    }

    context = {
        'page_title': 'Dashboard Administrador — EduPilot',
        'active_nav': 'dashboard',
        'stats': stats,
    }
    return render(request, 'admin/dashboard.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE ESTUDIANTES
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@user_passes_test(is_admin)
def admin_students_view(request):
    """
    Lista y gestión de estudiantes registrados.
    Fase 2: CRUD completo + filtros + exportación.
    """
    guard = _require_admin(request)
    if guard:
        return guard

    if request.method == 'POST' and request.POST.get('action') == 'create_student':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        student_code = request.POST.get('student_code')
        program_id = request.POST.get('program_id')
        current_semester = request.POST.get('current_semester')

        try:
            user = User.objects.create_user(
                username=student_code,
                email=email,
                password=student_code,  # Código como contraseña inicial
                first_name=first_name,
                last_name=last_name,
                role='STUDENT'
            )
            
            program_obj = AcademicProgram.objects.get(id=program_id) if program_id else None

            StudentProfile.objects.create(
                user=user,
                program=program_obj,
                current_semester=current_semester or 1
            )
            messages.success(request, 'Estudiante creado exitosamente.')
        except Exception as e:
            messages.error(request, f'Error al crear estudiante: Es posible que el código o correo ya exista.')
        
        return redirect('admin_panel:students')
    
    elif request.method == 'POST' and request.POST.get('action') == 'edit_student':
        student_id = request.POST.get('student_id')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        program_id = request.POST.get('program_id')
        current_semester = request.POST.get('current_semester')
        
        try:
            profile = StudentProfile.objects.get(id=student_id)
            profile.user.first_name = first_name
            profile.user.last_name = last_name
            profile.user.email = email
            profile.user.save()
            
            profile.program_id = program_id if program_id else None
            profile.current_semester = current_semester or 1
            profile.save()
            messages.success(request, 'Estudiante actualizado exitosamente.')
        except Exception as e:
            messages.error(request, 'Error al actualizar estudiante.')
        return redirect('admin_panel:students')

    elif request.method == 'POST' and request.POST.get('action') == 'delete_student':
        student_id = request.POST.get('student_id')
        try:
            profile = StudentProfile.objects.get(id=student_id)
            profile.user.delete()
            messages.success(request, 'Estudiante eliminado exitosamente.')
        except Exception as e:
            messages.error(request, 'Error al eliminar estudiante.')
        return redirect('admin_panel:students')

    students = StudentProfile.objects.select_related('user', 'program').all().order_by('-id')
    programs = AcademicProgram.objects.filter(is_active=True)

    q = request.GET.get('q', '').strip()
    program_filter = request.GET.get('program', '')

    if q:
        from django.db.models import Q
        students = students.filter(
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__username__icontains=q)
        )
    
    if program_filter:
        students = students.filter(program_id=program_filter)

    context = {
        'page_title': 'Gestión de Estudiantes — EduPilot',
        'active_nav': 'students',
        'students': students,
        'programs': programs,
    }
    return render(request, 'admin/estudiantes.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE MATERIAS
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@user_passes_test(is_admin)
def admin_courses_view(request):
    """
    Catálogo de materias y gestión de prerrequisitos.
    CRUD completo de Course con nuevos campos y agrupación.
    """
    guard = _require_admin(request)
    if guard:
        return guard

    if request.method == 'POST' and request.POST.get('action') == 'create_course':
        code = request.POST.get('code')
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        credits = request.POST.get('credits')
        level = request.POST.get('level')
        color = request.POST.get('color', 'blue')
        program_id = request.POST.get('program_id')
        prerequisites = request.POST.getlist('prerequisites')

        try:
            program = AcademicProgram.objects.get(id=program_id) if program_id else None
            course = Course.objects.create(
                code=code,
                name=name,
                description=description,
                credits=credits,
                level=level,
                color=color,
                program=program
            )
            
            from apps.courses.models import Prerequisite
            for req_id in prerequisites:
                if req_id:
                    Prerequisite.objects.create(
                        course=course,
                        required_course_id=req_id
                    )
            
            messages.success(request, 'Materia creada exitosamente.')
        except Exception as e:
            messages.error(request, 'Error al crear materia.')
        
        return redirect('admin_panel:courses')
        
    elif request.method == 'POST' and request.POST.get('action') == 'edit_course':
        course_id = request.POST.get('course_id')
        code = request.POST.get('code')
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        credits = request.POST.get('credits')
        level = request.POST.get('level')
        color = request.POST.get('color', 'blue')
        program_id = request.POST.get('program_id')
        prerequisites = request.POST.getlist('prerequisites')

        try:
            course = Course.objects.get(id=course_id)
            course.code = code
            course.name = name
            course.description = description
            course.credits = credits
            course.level = level
            course.color = color
            course.program_id = program_id if program_id else None
            course.save()
            
            from apps.courses.models import Prerequisite
            Prerequisite.objects.filter(course=course).delete()
            for req_id in prerequisites:
                if req_id and str(req_id) != str(course.id):  # Evitar que sea prerrequisito de sí misma
                    Prerequisite.objects.create(
                        course=course,
                        required_course_id=req_id
                    )

            messages.success(request, 'Materia actualizada exitosamente.')
        except Exception as e:
            messages.error(request, 'Error al actualizar materia.')
        
        return redirect('admin_panel:courses')

    elif request.method == 'POST' and request.POST.get('action') == 'delete_course':
        course_id = request.POST.get('course_id')
        try:
            course = Course.objects.get(id=course_id)
            course.delete()
            messages.success(request, 'Materia eliminada exitosamente.')
        except Exception as e:
            messages.error(request, 'Error al eliminar materia.')
        return redirect('admin_panel:courses')

    all_courses = Course.objects.all().order_by('name')
    courses = Course.objects.select_related('program').prefetch_related('course_prerequisites').all()

    # Filtros
    q = request.GET.get('q', '').strip()
    level_filter = request.GET.get('level', '')
    program_filter = request.GET.get('program', '')

    if q:
        from django.db.models import Q
        courses = courses.filter(
            Q(name__icontains=q) |
            Q(code__icontains=q)
        )
    
    if level_filter:
        courses = courses.filter(level=level_filter)
        
    if program_filter:
        courses = courses.filter(program_id=program_filter)

    courses = courses.order_by('level', 'name')
    
    # Agrupar por semestre
    grouped_courses = {}
    for c in courses:
        if c.level not in grouped_courses:
            grouped_courses[c.level] = []
        grouped_courses[c.level].append(c)
        
    programs = AcademicProgram.objects.filter(is_active=True)

    context = {
        'page_title': 'Gestión de Materias — EduPilot',
        'active_nav': 'courses',
        'grouped_courses': grouped_courses,
        'all_courses': all_courses,
        'programs': programs,
        'has_filters': bool(q or level_filter or program_filter)
    }
    return render(request, 'admin/reg_materias.html', context)
