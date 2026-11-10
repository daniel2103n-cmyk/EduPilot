"""
EduPilot — Views del Panel Administrador.

Responsabilidades:
  - Renderizar vistas del panel de administración
  - CRUD de estudiantes, materias, programas y visualización de horarios
  - Métricas reales de la base de datos
  - Verificar autenticación y rol ADMIN
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, Avg, Sum, Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.urls import reverse
import csv
import io

from apps.students.models import StudentProfile
from apps.academic.models import AcademicProgram, AcademicRecord
from apps.courses.models import Course, Prerequisite, CourseGroup

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
    Panel principal del administrador con métricas reales.
    """
    guard = _require_admin(request)
    if guard:
        return guard

    total_students = StudentProfile.objects.count()
    total_courses = Course.objects.count()
    total_programs = AcademicProgram.objects.filter(is_active=True).count()
    total_prerequisites = Prerequisite.objects.count()

    # Registros académicos para métricas de rendimiento
    total_records = AcademicRecord.objects.count()
    passed_records = AcademicRecord.objects.filter(status='PASSED').count()
    failed_records = AcademicRecord.objects.filter(status='FAILED').count()
    in_progress_records = AcademicRecord.objects.filter(status='IN_PROGRESS').count()

    pass_rate = round((passed_records / total_records * 100), 1) if total_records > 0 else 0.0

    recent_students = (
        StudentProfile.objects
        .select_related('user', 'program')
        .order_by('-id')[:8]
    )

    programs = (
        AcademicProgram.objects
        .annotate(
            student_count=Count('studentprofile', distinct=True),
            course_count=Count('courses', distinct=True)
        )
        .all()
    )

    courses_with_prereq_count = (
        Course.objects.filter(course_prerequisites__isnull=False).distinct().count()
    )

    stats = {
        'total_students': total_students,
        'total_courses': total_courses,
        'total_programs': total_programs,
        'total_prerequisites': total_prerequisites,
        'total_records': total_records,
        'passed_records': passed_records,
        'failed_records': failed_records,
        'in_progress_records': in_progress_records,
        'pass_rate': pass_rate,
        'courses_with_prereq_count': courses_with_prereq_count,
    }

    context = {
        'page_title': 'Dashboard Administrador — EduPilot',
        'active_nav': 'dashboard',
        'stats': stats,
        'recent_students': recent_students,
        'programs': programs,
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
    Lista y gestión de estudiantes registrados (CRUD completo y filtros).
    """
    guard = _require_admin(request)
    if guard:
        return guard

    if request.method == 'POST' and request.POST.get('action') == 'create_student':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        student_code = request.POST.get('student_code', '').strip()
        program_id = request.POST.get('program_id')
        current_semester = request.POST.get('current_semester') or 1

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
                current_semester=current_semester
            )
            messages.success(request, f'Estudiante {first_name} {last_name} creado exitosamente.')
        except Exception as e:
            messages.error(request, f'Error al crear estudiante: El código o correo ya existe.')
        
        return redirect('admin_panel:students')
    
    elif request.method == 'POST' and request.POST.get('action') == 'edit_student':
        student_id = request.POST.get('student_id')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        program_id = request.POST.get('program_id')
        current_semester = request.POST.get('current_semester') or 1
        
        try:
            profile = StudentProfile.objects.select_related('user').get(id=student_id)
            profile.user.first_name = first_name
            profile.user.last_name = last_name
            profile.user.email = email
            profile.user.save()
            
            profile.program_id = program_id if program_id else None
            profile.current_semester = int(current_semester)
            profile.save()
            messages.success(request, 'Estudiante actualizado exitosamente.')
        except Exception as e:
            messages.error(request, 'Error al actualizar estudiante.')
        return redirect('admin_panel:students')

    elif request.method == 'POST' and request.POST.get('action') == 'delete_student':
        student_id = request.POST.get('student_id')
        try:
            profile = StudentProfile.objects.select_related('user').get(id=student_id)
            user_to_delete = profile.user
            profile.delete()
            user_to_delete.delete()
            messages.success(request, 'Estudiante eliminado exitosamente.')
        except Exception as e:
            messages.error(request, 'Error al eliminar estudiante.')
        return redirect('admin_panel:students')

    students_qs = StudentProfile.objects.select_related('user', 'program').all().order_by('-id')
    programs = AcademicProgram.objects.filter(is_active=True)

    q = request.GET.get('q', '').strip()
    program_filter = request.GET.get('program', '').strip()
    semester_filter = request.GET.get('semester', '').strip()

    if q:
        students_qs = students_qs.filter(
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(user__email__icontains=q) |
            Q(user__username__icontains=q)
        )
    
    if program_filter:
        students_qs = students_qs.filter(program_id=program_filter)

    if semester_filter:
        try:
            students_qs = students_qs.filter(current_semester=int(semester_filter))
        except ValueError:
            pass

    # Calcular para cada estudiante créditos aprobados y progreso curricular
    students_with_meta = []
    for s in students_qs:
        records = AcademicRecord.objects.filter(student=s)
        passed_records = records.filter(status='PASSED').select_related('course')
        passed_credits = sum(r.course.credits for r in passed_records)
        failed_count = records.filter(status='FAILED').count()
        in_progress_count = records.filter(status='IN_PROGRESS').count()
        
        total_prog_courses = Course.objects.filter(program=s.program, is_active=True).count() if s.program_id else 0
        total_prog_credits = Course.objects.filter(program=s.program, is_active=True).aggregate(Sum('credits'))['credits__sum'] or 120
        progress_pct = round((passed_credits / total_prog_credits * 100)) if total_prog_credits > 0 else 0

        # Riesgo
        risk_label = 'Regular'
        risk_class = 'bg-tertiary-fixed/40 text-on-tertiary-container'
        if failed_count >= 2:
            risk_label = 'Riesgo crítico'
            risk_class = 'bg-error-container text-on-error-container border border-error/30'
        elif failed_count == 1:
            risk_label = 'Alerta preventiva'
            risk_class = 'bg-amber-100 text-amber-900 border border-amber-300'

        students_with_meta.append({
            'profile': s,
            'passed_credits': passed_credits,
            'total_prog_credits': total_prog_credits,
            'progress_pct': progress_pct,
            'failed_count': failed_count,
            'in_progress_count': in_progress_count,
            'risk_label': risk_label,
            'risk_class': risk_class,
        })

    risk_students_count = sum(1 for item in students_with_meta if item['failed_count'] > 0)
    incomplete_count = sum(1 for item in students_with_meta if not item['profile'].program_id)

    context = {
        'page_title': 'Gestión de Estudiantes — EduPilot',
        'active_nav': 'students',
        'students': students_with_meta,
        'total_students_count': StudentProfile.objects.count(),
        'filtered_count': len(students_with_meta),
        'risk_students_count': risk_students_count,
        'incomplete_count': incomplete_count,
        'programs': programs,
        'search_query': q,
        'selected_program': program_filter,
        'selected_semester': semester_filter,
    }
    return render(request, 'admin/estudiantes.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# DETALLE DEL ESTUDIANTE (EXPEDIENTE)
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@user_passes_test(is_admin)
def admin_student_detail_view(request, student_id):
    """
    Expediente académico detallado del estudiante para el administrador.
    """
    guard = _require_admin(request)
    if guard:
        return guard

    student = get_object_or_404(
        StudentProfile.objects.select_related('user', 'program'),
        id=student_id
    )

    from apps.students.views.student_views import _build_academic_summary
    academic_summary = _build_academic_summary(student)

    # Todos los registros académicos del estudiante ordenados
    records = (
        AcademicRecord.objects
        .filter(student=student)
        .select_related('course')
        .order_by('semester_taken', 'course__name')
    )

    # Agrupar registros por semestre
    records_by_semester = {}
    for r in records:
        sem = r.semester_taken
        if sem not in records_by_semester:
            records_by_semester[sem] = []
        records_by_semester[sem].append(r)

    sorted_records_semesters = []
    for sem, recs in sorted(records_by_semester.items()):
        graded = [r for r in recs if r.grade is not None]
        avg_sem = sum(r.grade for r in graded) / len(graded) if graded else None
        sem_credits = sum(r.course.credits for r in recs)
        sorted_records_semesters.append({
            'semester': sem,
            'records': recs,
            'average': round(avg_sem, 2) if avg_sem else None,
            'credits': sem_credits,
        })

    # Materias totales del programa y créditos totales
    total_program_courses = 0
    total_program_credits = 0
    if student.program_id:
        p_courses = Course.objects.filter(program=student.program, is_active=True)
        total_program_courses = p_courses.count()
        total_program_credits = p_courses.aggregate(Sum('credits'))['credits__sum'] or 0

    remaining_credits = max(0, total_program_credits - academic_summary['credits_approved'])

    context = {
        'page_title': f'Expediente — {student.user.get_full_name() or student.user.username}',
        'active_nav': 'students',
        'student': student,
        'academic_summary': academic_summary,
        'sorted_records_semesters': sorted_records_semesters,
        'total_records_count': records.count(),
        'total_program_courses': total_program_courses,
        'total_program_credits': total_program_credits,
        'remaining_credits': remaining_credits,
    }
    return render(request, 'admin/detalle_estudiante.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE MATERIAS Y PRERREQUISITOS
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@user_passes_test(is_admin)
def admin_courses_view(request):
    """
    Catálogo de materias y administración de prerrequisitos con paginación por semestre
    y gestión interactiva de dependencias.
    """
    guard = _require_admin(request)
    if guard:
        return guard

    # ── ACCIÓN: CREAR MATERIA ──────────────────────────────────────────────
    if request.method == 'POST' and request.POST.get('action') == 'create_course':
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        credits_raw = request.POST.get('credits', '')
        credits = int(credits_raw) if credits_raw.strip() != '' else 3
        level = request.POST.get('level') or 1
        color = request.POST.get('color', 'blue')
        program_id = request.POST.get('program_id')
        prerequisites = request.POST.getlist('prerequisites')

        try:
            program = AcademicProgram.objects.get(id=program_id) if program_id else None
            course = Course.objects.create(
                code=code,
                name=name,
                description=description,
                credits=int(credits),
                level=int(level),
                color=color,
                program=program
            )
            
            for req_id in prerequisites:
                if req_id and str(req_id) != str(course.id):
                    req_course = Course.objects.get(id=req_id)
                    prereq = Prerequisite(course=course, required_course=req_course)
                    prereq.full_clean()
                    prereq.save()
            
            messages.success(request, f'Materia "{name}" ({code}) creada exitosamente.')
            return redirect(f"{reverse('admin_panel:courses')}?semester={course.level}&selected_course={course.id}")
        except ValidationError as e:
            err_msg = '; '.join(e.messages) if hasattr(e, 'messages') else str(e)
            messages.error(request, f'Error en prerrequisitos: {err_msg}')
        except Exception as e:
            messages.error(request, f'Error al crear materia: {e}')
        
        return redirect('admin_panel:courses')
        
    # ── ACCIÓN: EDITAR MATERIA ─────────────────────────────────────────────
    elif request.method == 'POST' and request.POST.get('action') == 'edit_course':
        course_id = request.POST.get('course_id')
        code = request.POST.get('code', '').strip()
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        credits_raw = request.POST.get('credits', '')
        credits = int(credits_raw) if credits_raw.strip() != '' else 3
        level = request.POST.get('level') or 1
        color = request.POST.get('color', 'blue')
        program_id = request.POST.get('program_id')
        prerequisites = request.POST.getlist('prerequisites')

        try:
            course = Course.objects.get(id=course_id)
            new_level = int(level)
            
            # Validar si el nuevo nivel entra en conflicto con materias que dependen de ella
            violating_deps = course.required_for.filter(course__level__lte=new_level)
            if violating_deps.exists():
                dep_names = ", ".join([f"{d.course.name} (Semestre {d.course.level})" for d in violating_deps])
                raise ValidationError(
                    f"No puedes mover esta materia al Semestre {new_level} porque materias que dependen de ella ({dep_names}) "
                    f"están en un semestre igual o menor."
                )

            course.code = code
            course.name = name
            course.description = description
            course.credits = int(credits)
            course.level = new_level
            course.color = color
            course.program_id = program_id if program_id else None
            course.save()
            
            # Recrear prerrequisitos validados
            Prerequisite.objects.filter(course=course).delete()
            for req_id in prerequisites:
                if req_id and str(req_id) != str(course.id):
                    req_course = Course.objects.get(id=req_id)
                    prereq = Prerequisite(course=course, required_course=req_course)
                    prereq.full_clean()
                    prereq.save()

            messages.success(request, f'Materia "{name}" actualizada exitosamente.')
            return redirect(f"{reverse('admin_panel:courses')}?semester={course.level}&selected_course={course.id}")
        except ValidationError as e:
            err_msg = '; '.join(e.messages) if hasattr(e, 'messages') else str(e)
            messages.error(request, f'Error de validación: {err_msg}')
        except Exception as e:
            messages.error(request, f'Error al actualizar materia: {e}')
        
        return redirect('admin_panel:courses')

    # ── ACCIÓN: AGREGAR PRERREQUISITO DIRECTO (DESDE EL GRAFO) ──────────────
    elif request.method == 'POST' and request.POST.get('action') == 'add_prerequisite':
        course_id = request.POST.get('course_id')
        required_course_id = request.POST.get('required_course_id')
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('format') == 'json'

        try:
            course = Course.objects.get(id=course_id)
            req_course = Course.objects.get(id=required_course_id)

            prereq = Prerequisite(course=course, required_course=req_course)
            prereq.full_clean()
            prereq.save()

            msg = f'Prerrequisito "{req_course.name}" añadido exitosamente a "{course.name}".'
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': msg,
                    'prerequisite': {
                        'id': req_course.id,
                        'code': req_course.code,
                        'name': req_course.name,
                        'level': req_course.level,
                        'credits': req_course.credits
                    }
                })
            messages.success(request, msg)
            return redirect(f"{reverse('admin_panel:courses')}?semester={course.level}&selected_course={course.id}")
        except ValidationError as e:
            err_msg = '; '.join(e.messages) if hasattr(e, 'messages') else str(e)
            if is_ajax:
                return JsonResponse({'success': False, 'message': err_msg}, status=400)
            messages.error(request, err_msg)
        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, f'Error al agregar prerrequisito: {e}')
        
        return redirect(f"{reverse('admin_panel:courses')}?selected_course={course_id}")

    # ── ACCIÓN: ELIMINAR PRERREQUISITO DIRECTO (DESDE EL GRAFO) ────────────
    elif request.method == 'POST' and request.POST.get('action') == 'remove_prerequisite':
        course_id = request.POST.get('course_id')
        required_course_id = request.POST.get('required_course_id')
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('format') == 'json'

        try:
            course = Course.objects.get(id=course_id)
            deleted_count, _ = Prerequisite.objects.filter(
                course_id=course_id,
                required_course_id=required_course_id
            ).delete()

            if deleted_count > 0:
                msg = 'Prerrequisito desvinculado exitosamente.'
                if is_ajax:
                    return JsonResponse({'success': True, 'message': msg})
                messages.success(request, msg)
            else:
                msg = 'No se encontró el prerrequisito especificado.'
                if is_ajax:
                    return JsonResponse({'success': False, 'message': msg}, status=404)
                messages.warning(request, msg)
            return redirect(f"{reverse('admin_panel:courses')}?semester={course.level}&selected_course={course.id}")
        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, f'Error al eliminar prerrequisito: {e}')

        return redirect(f"{reverse('admin_panel:courses')}?selected_course={course_id}")

    # ── ACCIÓN: ELIMINAR MATERIA ───────────────────────────────────────────
    elif request.method == 'POST' and request.POST.get('action') == 'delete_course':
        course_id = request.POST.get('course_id')
        try:
            course = Course.objects.get(id=course_id)
            course_name = course.name
            course_level = course.level
            course.delete()
            messages.success(request, f'Materia "{course_name}" eliminada exitosamente.')
            return redirect(f"{reverse('admin_panel:courses')}?semester={course_level}")
        except Exception as e:
            messages.error(request, 'Error al eliminar materia.')
        return redirect('admin_panel:courses')

    # ── CONSULTA BASE Y FILTROS ────────────────────────────────────────────
    all_courses = (
        Course.objects
        .select_related('program')
        .all()
        .order_by('level', 'name')
    )
    
    courses_qs = (
        Course.objects
        .select_related('program')
        .prefetch_related('course_prerequisites__required_course', 'required_for__course')
        .all()
    )

    q = request.GET.get('q', '').strip()
    program_filter = request.GET.get('program', '').strip()

    if q:
        courses_qs = courses_qs.filter(
            Q(name__icontains=q) |
            Q(code__icontains=q)
        )
        
    if program_filter:
        courses_qs = courses_qs.filter(program_id=program_filter)

    # ── PAGINACIÓN POR SEMESTRE ────────────────────────────────────────────
    # Obtenemos todos los semestres distintos existentes en la base de datos
    existing_levels = sorted(list(Course.objects.values_list('level', flat=True).distinct()))
    if not existing_levels:
        existing_levels = list(range(1, 11))
    else:
        # Asegurar al menos cubrir hasta el nivel máximo o 10
        max_lvl = max(max(existing_levels), 10)
        existing_levels = list(range(1, max_lvl + 1))

    # Estadísticas por semestre (para botones y pills de navegación)
    semesters_nav = []
    for lvl in existing_levels:
        lvl_qs = Course.objects.filter(level=lvl)
        if program_filter:
            lvl_qs = lvl_qs.filter(program_id=program_filter)
        semesters_nav.append({
            'number': lvl,
            'count': lvl_qs.count(),
            'credits': lvl_qs.aggregate(s=Sum('credits'))['s'] or 0
        })

    semester_param = request.GET.get('semester', '').strip()
    if semester_param == 'all':
        current_semester = 'all'
        active_level_int = None
    elif semester_param.isdigit() and int(semester_param) in existing_levels:
        current_semester = int(semester_param)
        active_level_int = int(semester_param)
    else:
        # Por defecto, el primer semestre que tenga materias o Semestre 1
        first_with_courses = next((s['number'] for s in semesters_nav if s['count'] > 0), 1)
        current_semester = first_with_courses
        active_level_int = first_with_courses

    # Filtrar asignaturas por semestre seleccionado si no es 'all'
    if current_semester != 'all':
        display_courses = courses_qs.filter(level=current_semester).order_by('name')
    else:
        display_courses = courses_qs.order_by('level', 'name')

    # Calcular anterior y siguiente para navegación
    prev_semester = None
    next_semester = None
    if isinstance(current_semester, int):
        idx = existing_levels.index(current_semester) if current_semester in existing_levels else -1
        if idx > 0:
            prev_semester = existing_levels[idx - 1]
        if idx >= 0 and idx < len(existing_levels) - 1:
            next_semester = existing_levels[idx + 1]

    programs = AcademicProgram.objects.filter(is_active=True)

    # Estadísticas globales para las tarjetas KPI
    total_courses_count = Course.objects.count()
    courses_with_prereq_count = Course.objects.filter(course_prerequisites__isnull=False).distinct().count()
    prereq_percentage = round((courses_with_prereq_count / total_courses_count * 100), 1) if total_courses_count > 0 else 0

    stats = {
        'total_courses': total_courses_count,
        'courses_with_prereq': courses_with_prereq_count,
        'prereq_percentage': prereq_percentage,
        'total_programs': programs.count(),
    }

    # Datos para renderizar información del semestre activo
    current_semester_stats = None
    if isinstance(current_semester, int):
        current_semester_stats = next((s for s in semesters_nav if s['number'] == current_semester), None)

    context = {
        'page_title': 'Materias y Prerrequisitos — EduPilot',
        'active_nav': 'courses',
        'courses': display_courses,
        'all_courses': all_courses,
        'programs': programs,
        'stats': stats,
        'semesters_nav': semesters_nav,
        'current_semester': current_semester,
        'current_semester_stats': current_semester_stats,
        'prev_semester': prev_semester,
        'next_semester': next_semester,
        'selected_course_id': request.GET.get('selected_course', '').strip(),
        'has_filters': bool(q or program_filter),
        'search_query': q,
        'selected_program': program_filter,
    }
    return render(request, 'admin/materias.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# PROGRAMAS ACADÉMICOS
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@user_passes_test(is_admin)
def admin_programs_view(request):
    """
    Gestión de programas académicos y facultades.
    """
    guard = _require_admin(request)
    if guard:
        return guard

    if request.method == 'POST' and request.POST.get('action') == 'create_program':
        name = request.POST.get('name', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        if name:
            AcademicProgram.objects.create(name=name, is_active=is_active)
            messages.success(request, f'Programa "{name}" creado exitosamente.')
        else:
            messages.error(request, 'El nombre del programa es obligatorio.')
        return redirect('admin_panel:programs')

    elif request.method == 'POST' and request.POST.get('action') == 'toggle_program':
        program_id = request.POST.get('program_id')
        try:
            p = AcademicProgram.objects.get(id=program_id)
            p.is_active = not p.is_active
            p.save()
            messages.success(request, f'Estado del programa "{p.name}" actualizado.')
        except Exception:
            messages.error(request, 'No se pudo actualizar el programa.')
        return redirect('admin_panel:programs')

    elif request.method == 'POST' and request.POST.get('action') == 'edit_program':
        program_id = request.POST.get('program_id')
        name = request.POST.get('name', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        try:
            p = AcademicProgram.objects.get(id=program_id)
            if name:
                p.name = name
                p.is_active = is_active
                p.save()
                messages.success(request, f'Programa "{name}" actualizado exitosamente.')
            else:
                messages.error(request, 'El nombre del programa es obligatorio.')
        except Exception:
            messages.error(request, 'Error al actualizar el programa.')
        return redirect('admin_panel:programs')

    q = request.GET.get('q', '').strip()
    programs_qs = (
        AcademicProgram.objects
        .annotate(
            student_count=Count('studentprofile', distinct=True),
            course_count=Count('courses', distinct=True)
        )
        .all()
        .order_by('name')
    )

    if q:
        programs_qs = programs_qs.filter(name__icontains=q)

    # Calcular créditos totales por programa
    programs_data = []
    total_students_enrolled = 0
    for prog in programs_qs:
        total_creds = Course.objects.filter(program=prog, is_active=True).aggregate(Sum('credits'))['credits__sum'] or 0
        total_students_enrolled += prog.student_count
        programs_data.append({
            'program': prog,
            'student_count': prog.student_count,
            'course_count': prog.course_count,
            'total_credits': total_creds,
        })

    stats = {
        'total_programs': AcademicProgram.objects.count(),
        'active_programs': AcademicProgram.objects.filter(is_active=True).count(),
        'inactive_programs': AcademicProgram.objects.filter(is_active=False).count(),
        'total_students_enrolled': total_students_enrolled,
    }

    context = {
        'page_title': 'Programas Académicos — EduPilot',
        'active_nav': 'programs',
        'programs_data': programs_data,
        'stats': stats,
        'search_query': q,
    }
    return render(request, 'admin/programas.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# HORARIOS Y GRUPOS (ADMINISTRATIVO)
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
@user_passes_test(is_admin)
def admin_schedules_view(request):
    """
    Planificación de horarios, grupos y secciones para asignaturas.
    Permite importar desde CSV con el formato institucional.
    """
    guard = _require_admin(request)
    if guard:
        return guard

    import_errors = []
    import_success_count = 0

    # ── Importar CSV ─────────────────────────────────────────────────────────
    if request.method == 'POST' and request.POST.get('action') == 'import_csv':
        csv_file = request.FILES.get('csv_file')
        replace_all = request.POST.get('replace_all') == 'on'

        if not csv_file:
            messages.error(request, 'Debes seleccionar un archivo CSV.')
        elif not csv_file.name.endswith('.csv'):
            messages.error(request, 'El archivo debe ser de tipo CSV (.csv).')
        else:
            try:
                if replace_all:
                    CourseGroup.objects.all().delete()

                decoded = csv_file.read().decode('utf-8-sig', errors='replace')
                reader = csv.reader(io.StringIO(decoded), delimiter=',')

                from datetime import time as dtime

                def parse_time_flexible(val):
                    if not val:
                        return None
                    v = str(val).strip().replace('.', ':')
                    if not v or v.lower() in ('--', '-', 'n/a', 'null', 'none', 'grupo sin horario'):
                        return None
                    if ':' in v:
                        parts = v.split(':')
                        try:
                            h = int(parts[0])
                            m = int(parts[1]) if len(parts) > 1 else 0
                            if 0 <= h <= 23 and 0 <= m <= 59:
                                return dtime(hour=h, minute=m)
                        except (ValueError, TypeError):
                            return None
                    # Formato numérico militar (700 -> 07:00, 959 -> 09:59, 1000 -> 10:00, 1600 -> 16:00)
                    try:
                        num = int(v)
                        h = num // 100
                        m = num % 100
                        if 0 <= h <= 23 and 0 <= m <= 59:
                            return dtime(hour=h, minute=m)
                    except (ValueError, TypeError):
                        pass
                    return None

                def normalize_day(d):
                    if not d:
                        return 'Sin Horario'
                    d_clean = str(d).strip()
                    d_upper = d_clean.upper()
                    if 'SIN HORARIO' in d_upper or not d_clean or d_clean in ('--', '-'):
                        return 'Sin Horario'
                    mapping = {
                        'LUNES': 'Lunes',
                        'MARTES': 'Martes',
                        'MIERCOLES': 'Miércoles',
                        'MIÉRCOLES': 'Miércoles',
                        'JUEVES': 'Jueves',
                        'VIERNES': 'Viernes',
                        'SABADO': 'Sábado',
                        'SÁBADO': 'Sábado',
                        'DOMINGO': 'Domingo'
                    }
                    return mapping.get(d_upper, d_clean.title())

                last_semester = 1
                last_learning_field = ''
                last_code = ''
                last_group = ''
                last_spots = 0

                groups_to_create = []
                row_num = 0

                for raw_cols in reader:
                    row_num += 1
                    if not raw_cols or all(c.strip() == '' for c in raw_cols):
                        continue

                    # Rellenar con cadenas vacías si la fila tiene menos de 9 columnas
                    cols = [c.strip() for c in raw_cols] + [''] * max(0, 9 - len(raw_cols))

                    sem_val = cols[0]
                    name_val = cols[1]
                    code_val = cols[2]
                    group_val = cols[3]
                    spots_val = cols[4]
                    day_val = cols[5]
                    start_val = cols[6]
                    end_val = cols[7]
                    class_val = cols[8]

                    # Detectar si es fila de encabezado
                    if (
                        sem_val.lower() in ('semestre', 'sem')
                        or 'campo de aprendizaje' in name_val.lower()
                        or 'código' in code_val.lower()
                        or 'codigo' in code_val.lower()
                    ):
                        continue

                    # Actualizar valores heredados (forward-fill de celdas combinadas)
                    if sem_val:
                        try:
                            last_semester = int(sem_val)
                        except (ValueError, TypeError):
                            pass

                    if name_val:
                        last_learning_field = name_val

                    if code_val:
                        last_code = code_val

                    if group_val:
                        last_group = group_val

                    if spots_val:
                        try:
                            last_spots = int(spots_val)
                        except (ValueError, TypeError):
                            pass

                    if not last_code or not last_group:
                        import_errors.append(f"Fila {row_num}: No se pudo determinar el código o grupo de la asignatura.")
                        continue

                    day = normalize_day(day_val)
                    start_time = parse_time_flexible(start_val)
                    end_time = parse_time_flexible(end_val)
                    classroom = class_val if class_val else '--'

                    # Buscar o crear automáticamente la asignatura en Course si no existe
                    from apps.courses.services import CourseSyncService
                    linked_course, was_created = CourseSyncService.get_or_create_course_for_import(
                        code=last_code,
                        name=last_learning_field,
                        semester=last_semester
                    )
                    course_name = last_learning_field or (linked_course.name if linked_course else '')

                    groups_to_create.append(CourseGroup(
                        semester=last_semester,
                        learning_field=last_learning_field,
                        course_code=last_code,
                        course_name=course_name,
                        group_number=last_group,
                        available_spots=last_spots,
                        day=day,
                        start_time=start_time,
                        end_time=end_time,
                        classroom=classroom,
                        course=linked_course,
                    ))

                if groups_to_create:
                    CourseGroup.objects.bulk_create(groups_to_create)
                    import_success_count = len(groups_to_create)

                if import_success_count:
                    messages.success(request, f'✓ {import_success_count} horarios y grupos importados exitosamente. Asignaturas sincronizadas automáticamente con el catálogo.')
                if import_errors:
                    messages.warning(request, f'Se procesaron {import_success_count} registros, pero hubo {len(import_errors)} filas no procesables.')

            except Exception as e:
                messages.error(request, f'Error al procesar el archivo CSV: {e}')

        return redirect('admin_panel:schedules')

    # ── Sincronizar asignaturas huérfanas desde grupos de horarios ────────────
    if request.method == 'POST' and request.POST.get('action') == 'sync_courses':
        from apps.courses.services import CourseSyncService
        res = CourseSyncService.sync_unlinked_groups()
        messages.success(
            request,
            f"✓ Sincronización completada: {res['courses_created']} asignaturas creadas en el plan de estudios y {res['groups_linked']} grupos vinculados exitosamente."
        )
        return redirect('admin_panel:schedules')

    # ── Eliminar grupo ────────────────────────────────────────────────────────
    if request.method == 'POST' and request.POST.get('action') == 'delete_group':
        group_id = request.POST.get('group_id')
        try:
            grp = CourseGroup.objects.get(id=group_id)
            grp.delete()
            messages.success(request, 'Grupo eliminado exitosamente.')
        except CourseGroup.DoesNotExist:
            messages.error(request, 'Grupo no encontrado.')
        return redirect('admin_panel:schedules')

    # ── Limpiar todos los grupos ──────────────────────────────────────────────
    if request.method == 'POST' and request.POST.get('action') == 'clear_all':
        count = CourseGroup.objects.count()
        CourseGroup.objects.all().delete()
        messages.success(request, f'{count} grupos eliminados.')
        return redirect('admin_panel:schedules')

    # ── Filtros de consulta ───────────────────────────────────────────────────
    q = request.GET.get('q', '').strip()
    semester_filter = request.GET.get('semester', '').strip()
    day_filter = request.GET.get('day', '').strip()
    program_filter = request.GET.get('program', '').strip()
    spots_filter = request.GET.get('spots', '').strip()

    groups_qs = CourseGroup.objects.select_related('course__program').all()

    if q:
        groups_qs = groups_qs.filter(
            Q(course_code__icontains=q) |
            Q(course_name__icontains=q) |
            Q(classroom__icontains=q) |
            Q(learning_field__icontains=q) |
            Q(group_number__icontains=q)
        )
    if semester_filter:
        try:
            groups_qs = groups_qs.filter(semester=int(semester_filter))
        except ValueError:
            pass
    if day_filter:
        groups_qs = groups_qs.filter(day=day_filter)
    if program_filter:
        program_codes = Course.objects.filter(program_id=program_filter).values_list('code', flat=True)
        groups_qs = groups_qs.filter(
            Q(course__program_id=program_filter) |
            Q(course_code__in=program_codes)
        )
    if spots_filter == 'available':
        groups_qs = groups_qs.filter(available_spots__gt=0)
    elif spots_filter == 'full':
        groups_qs = groups_qs.filter(available_spots=0)

    # ── Estadísticas Globales ──────────────────────────────────────────────────
    total_groups = CourseGroup.objects.count()
    total_spots = CourseGroup.objects.aggregate(s=Sum('available_spots'))['s'] or 0
    unique_codes = CourseGroup.objects.order_by().values('course_code').distinct().count()

    # ── Opciones Únicas para Filtros (sin duplicados y orden canónico) ──────────
    semesters = sorted([s for s in set(CourseGroup.objects.order_by().values_list('semester', flat=True)) if s is not None])
    canonical_days = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo', 'Sin Horario']
    existing_days = set(CourseGroup.objects.order_by().values_list('day', flat=True))
    days = [d for d in canonical_days if d in existing_days]
    extra_days = sorted(list(existing_days - set(canonical_days) - {None, ''}))
    days.extend(extra_days)

    days_covered = len([d for d in days if d != 'Sin Horario'])
    programs = AcademicProgram.objects.filter(is_active=True).order_by('name')

    # Métricas filtradas
    filtered_count = groups_qs.count()
    filtered_spots = groups_qs.aggregate(s=Sum('available_spots'))['s'] or 0

    stats = {
        'total_groups': total_groups,
        'total_spots': total_spots,
        'unique_courses': unique_codes,
        'days_covered': days_covered,
        'filtered_count': filtered_count,
        'filtered_spots': filtered_spots,
    }

    # ── Paginación ────────────────────────────────────────────────────────────
    per_page = 30
    page_number = request.GET.get('page', 1)
    paginator = Paginator(groups_qs, per_page)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # Querystring para paginador sin parámetro page
    get_params = request.GET.copy()
    if 'page' in get_params:
        get_params.pop('page')
    querystring = get_params.urlencode()

    has_active_filters = bool(q or semester_filter or day_filter or program_filter or spots_filter)

    context = {
        'page_title': 'Horarios y Grupos — EduPilot',
        'active_nav': 'schedules',
        'page_obj': page_obj,
        'groups': page_obj,  # Compatibilidad y paginado
        'paginator': paginator,
        'querystring': querystring,
        'programs': programs,
        'stats': stats,
        'semesters': semesters,
        'days': days,
        'import_errors': import_errors,
        'search_query': q,
        'selected_semester': semester_filter,
        'selected_day': day_filter,
        'selected_program': program_filter,
        'selected_spots': spots_filter,
        'has_active_filters': has_active_filters,
        'has_data': total_groups > 0,
        'col_list': [
            'SEMESTRE', 'CAMPO DE APRENDIZAJE / NUCLEO TEMATICO',
            'CÓDIGO', 'GRUPO', 'CUPOS DISPONIBLES',
            'DÍA', 'HORA INICIO', 'HORA FIN', 'SALÓN'
        ],
    }
    return render(request, 'admin/horarios.html', context)


