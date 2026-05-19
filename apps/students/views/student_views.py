"""
EduPilot — Views del Panel Estudiante.

Responsabilidades:
  - Renderizar vistas del área del estudiante
  - Calcular métricas académicas reales mediante ORM
  - Verificar autenticación con login_required
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.db.models import Avg, Sum, Count

from apps.academic.models import AcademicRecord
from apps.students.models import StudentProfile


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_student_profile(request):
    """
    Retorna el StudentProfile del usuario autenticado,
    o None si no existe (ej. admin sin perfil de estudiante).
    """
    try:
        return request.user.studentprofile
    except StudentProfile.DoesNotExist:
        return None


def _build_academic_summary(profile):
    """
    Calcula las métricas académicas del estudiante a partir de AcademicRecord.

    Retorna un dict con:
      - courses_passed      → materias aprobadas
      - courses_failed      → materias reprobadas
      - courses_in_progress → materias en curso
      - credits_approved    → suma de créditos aprobados
      - average_grade       → promedio general (solo materias con nota)
      - progress_pct        → % de avance respecto al total del programa
    """
    if profile is None:
        return {
            'courses_passed':      0,
            'courses_failed':      0,
            'courses_in_progress': 0,
            'credits_approved':    0,
            'average_grade':       None,
            'progress_pct':        0,
            'has_lost_student_status': False,
        }

    records = AcademicRecord.objects.filter(student=profile)

    # Conteos por estado
    counts = records.values('status').annotate(total=Count('id'))
    status_map = {item['status']: item['total'] for item in counts}

    passed      = status_map.get('PASSED', 0)
    failed      = status_map.get('FAILED', 0)
    in_progress = status_map.get('IN_PROGRESS', 0)

    # Créditos aprobados — select_related para acceder a course.credits sin N+1
    credits_approved = (
        records
        .filter(status='PASSED')
        .select_related('course')
        .aggregate(total=Sum('course__credits'))['total'] or 0
    )

    # Promedio general (solo registros con nota, excluyendo IN_PROGRESS sin nota)
    avg_result = (
        records
        .exclude(status='IN_PROGRESS')
        .aggregate(avg=Avg('grade'))['avg']
    )
    average_grade = round(avg_result, 2) if avg_result is not None else None

    # % de avance: aprobadas / total materias del programa
    total_program_courses = 0
    if profile.program_id:
        from apps.courses.models import Course
        total_program_courses = Course.objects.filter(
            program=profile.program,
            is_active=True
        ).count()

    progress_pct = 0
    if total_program_courses > 0:
        progress_pct = round((passed / total_program_courses) * 100)

    # Pérdida de calidad de estudiante
    has_lost_student_status = False
    # Solo evalúa la pérdida de calidad si NO tiene materias en curso
    if in_progress == 0:
        if average_grade is not None and average_grade < 3.2:
            has_lost_student_status = True
        else:
            # Verifica si hay 3 fallos en alguna materia
            failed_counts = records.filter(status='FAILED').values('course_id').annotate(fails=Count('id')).filter(fails__gte=3)
            if failed_counts.exists():
                has_lost_student_status = True

    return {
        'courses_passed':      passed,
        'courses_failed':      failed,
        'courses_in_progress': in_progress,
        'credits_approved':    credits_approved,
        'average_grade':       average_grade,
        'progress_pct':        progress_pct,
        'has_lost_student_status': has_lost_student_status,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD ESTUDIANTE
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
def student_dashboard_view(request):
    """
    Dashboard principal del estudiante.

    Context:
      - academic_summary   → dict con métricas calculadas
      - academic_records   → QuerySet de AcademicRecord con course pre-cargado
      - profile            → StudentProfile del usuario (puede ser None)
    """
    profile = _get_student_profile(request)

    academic_summary = _build_academic_summary(profile)

    # ── Construir tabla de historial completo ──────────────────────────────
    # Incluye TODAS las materias del programa, con estado desde AcademicRecord
    # (o PENDING si no existe registro aún).
    all_courses_with_status = []

    if profile and profile.program_id:
        from apps.courses.models import Course

        program_courses = (
            Course.objects
            .filter(program=profile.program, is_active=True)
            .order_by('level', 'name')
        )

        # Mapa course_id → AcademicRecord (una sola query)
        record_map = {
            r.course_id: r
            for r in AcademicRecord.objects.filter(
                student=profile
            ).select_related('course')
        }

        for course in program_courses:
            record = record_map.get(course.id)
            all_courses_with_status.append({
                'course':  course,
                'status':  record.status if record else 'PENDING',
                'grade':   record.grade  if record else None,
            })

    context = {
        'page_title':               'Mi Dashboard — EduPilot',
        'active_nav':               'dashboard',
        'profile':                  profile,
        'academic_summary':         academic_summary,
        'all_courses_with_status':  all_courses_with_status,
    }
    return render(request, 'estudiantes/dashboard_est.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# MATERIAS DEL ESTUDIANTE
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
def student_courses_view(request):
    """
    Vista de materias del estudiante organizadas por estado.

    Context:
      - courses_in_progress  → materias actualmente en curso
      - courses_passed       → materias aprobadas (ordenadas por semestre)
      - courses_failed       → materias reprobadas
      - courses_pending      → materias sin registro (por cursar)
      - counts               → dict con totales por grupo + créditos aprobados
      - profile              → StudentProfile
    """
    from apps.courses.models import Course

    profile = _get_student_profile(request)
    academic_summary = _build_academic_summary(profile)

    # ── Contadores globales ──────────────────────────────────────────────
    courses_in_progress = 0
    courses_passed      = 0
    courses_failed      = 0
    courses_pending     = 0
    credits_approved    = 0

    # ── Agrupamiento por semestres (Línea de tiempo real) ────────────────────
    # Estructura: { 1: [item1, item2], 2: [item3], ... }
    semesters_dict = {}
    banco_materias = []

    if profile and profile.program_id:
        program_courses = (
            Course.objects
            .filter(program=profile.program, is_active=True)
            .order_by('level', 'name')
        )

        # Todos los registros del estudiante
        records = list(AcademicRecord.objects.filter(student=profile).select_related('course'))

        # 1. Agrupar los registros existentes en su respectivo semestre
        for record in records:
            level = record.semester_taken
            if level not in semesters_dict:
                semesters_dict[level] = []

            item = {
                'course': record.course,
                'status': record.status,
                'grade':  record.grade,
                'record_id': record.id,
                'semester_taken': record.semester_taken,
            }
            semesters_dict[level].append(item)

            if record.status == 'IN_PROGRESS':
                courses_in_progress += 1
            elif record.status == 'PASSED':
                courses_passed += 1
                credits_approved += record.course.credits
            elif record.status == 'FAILED':
                courses_failed += 1

        # 2. Generar el "Banco de Materias" (Pendientes o para repetir)
        for course in program_courses:
            # Buscamos si el estudiante ya la pasó o la está viendo
            course_records = [r for r in records if r.course_id == course.id]
            is_active_or_passed = any(r.status in ['PASSED', 'IN_PROGRESS'] for r in course_records)
            
            if not is_active_or_passed:
                attempts = len(course_records) + 1
                item = {
                    'course': course,
                    'status': 'PENDING',
                    'grade': None,
                    'record_id': None,
                    'semester_taken': course.level, # Semestre original por defecto
                    'attempt': attempts
                }
                banco_materias.append(item)
                courses_pending += 1

    counts = {
        'in_progress':      courses_in_progress,
        'passed':           courses_passed,
        'failed':           courses_failed,
        'pending':          courses_pending,
        'total':            (courses_in_progress + courses_passed + courses_failed + courses_pending),
        'credits_approved': credits_approved,
    }

    # Ordenar los semestres y calcular su promedio
    sorted_semesters = []
    for level, courses in sorted(semesters_dict.items()):
        graded_courses = [c for c in courses if c['status'] in ['PASSED', 'FAILED'] and c['grade'] is not None]
        avg = sum(c['grade'] for c in graded_courses) / len(graded_courses) if graded_courses else 0.0
        sorted_semesters.append({
            'level': level,
            'courses': courses,
            'average': avg,
            'has_grades': len(graded_courses) > 0
        })

    context = {
        'page_title':       'Mis Materias — EduPilot',
        'active_nav':       'courses',
        'profile':          profile,
        'sorted_semesters': sorted_semesters,
        'banco_materias':   banco_materias,
        'counts':           counts,
        'academic_summary': academic_summary,
    }
    return render(request, 'estudiantes/materias.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# RUTAS ACADÉMICAS
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@login_required
def student_routes_view(request):
    """
    Vista de rutas académicas recomendadas.

    Parámetros GET opcionales:
      ?strategy=BALANCED | FAST_TRACK | LIGHT   (default: BALANCED)

    Flujo:
      1. RouteGeneratorService calcula la ruta (lógica Django)
      2. AIService explica la ruta en lenguaje natural (OpenRouter)
      3. Ambos resultados se pasan al template

    Context:
      - route          → RouteResult con semesters, métricas y error si aplica
      - strategy       → string de la estrategia activa
      - all_strategies → lista de (key, label) para el selector
      - ai_explanation → str con la explicación de Mistral-7B (o fallback)
    """
    from services.route_generator import RouteGeneratorService, Strategy
    from apps.ai.services.ai_service import ai_service

    profile = _get_student_profile(request)

    # ── 1. Leer estrategia desde GET ─────────────────────────────────────────
    strategy = request.GET.get('strategy', Strategy.BALANCED).upper()
    if strategy not in Strategy.ALL:
        strategy = Strategy.BALANCED

    # ── 2. Generar ruta académica (Django — sin IA) ──────────────────────────
    route = RouteGeneratorService.generate(profile=profile, strategy=strategy)

    # ── 3. Explicar ruta con IA (solo si hay materias disponibles) ───────────
    ai_explanation = ''
    if profile and not route.is_empty:
        ai_explanation = ai_service.explain_route(profile=profile, route=route)

    context = {
        'page_title':      'Rutas Académicas — EduPilot',
        'active_nav':      'routes',
        'profile':         profile,
        'route':           route,
        'strategy':        strategy,
        'all_strategies':  [
            (key, Strategy.LABELS[key]) for key in Strategy.ALL
        ],
        'ai_explanation':  ai_explanation,
    }
    return render(request, 'estudiantes/rutas.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE HISTORIAL ACADÉMICO (AUTOFILL Y UPDATE)
# ─────────────────────────────────────────────────────────────────────────────
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
import json

@login_required
def autofill_records_view(request):
    """
    Rellena el historial del estudiante simulando sus semestres pasados.
    """
    if request.method == 'POST':
        profile = _get_student_profile(request)
        if profile:
            from apps.academic.services import AcademicService
            records_created = AcademicService.autofill_academic_records(profile)
            if records_created > 0:
                messages.success(request, f'Se autocompletaron {records_created} materias según tu semestre.')
            else:
                messages.info(request, 'No se generaron nuevas materias. Puede que ya tengas registros o falten prerrequisitos.')
    return redirect('student:courses')

@login_required
def update_academic_record_view(request):
    """
    Endpoint AJAX para que el estudiante actualice el estado de una materia.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            course_id = data.get('course_id')
            record_id = data.get('record_id')
            status = data.get('status')
            grade = data.get('grade')
            semester_taken = data.get('semester_taken')

            profile = _get_student_profile(request)
            if not profile:
                return JsonResponse({'success': False, 'error': 'Perfil no encontrado'}, status=400)

            from apps.academic.models import AcademicRecord
            from apps.courses.models import Course

            # Validar nota y semestre
            try:
                grade = float(grade) if grade else 0.0
            except ValueError:
                grade = 0.0
                
            try:
                semester_taken = int(semester_taken) if semester_taken else profile.current_semester
            except ValueError:
                semester_taken = profile.current_semester

            # Lógica automática de aprobación/reprobación según nota
            if status in ['PASSED', 'FAILED']:
                if grade < 3.0:
                    status = 'FAILED'
                else:
                    status = 'PASSED'

            # ---------------------------------------------------------
            # VALIDACIÓN DE LÍMITE DE CRÉDITOS (Max 18 por semestre)
            # ---------------------------------------------------------
            course_obj = None
            if course_id:
                course_obj = Course.objects.filter(id=course_id).first()
            elif record_id:
                record_to_check = AcademicRecord.objects.filter(id=record_id).select_related('course').first()
                if record_to_check:
                    course_obj = record_to_check.course

            if course_obj and status != 'PENDING':
                # Calcular cuántos créditos tiene registrados en `semester_taken` actualmente
                current_credits = AcademicRecord.objects.filter(
                    student=profile,
                    semester_taken=semester_taken
                )
                if record_id:
                    current_credits = current_credits.exclude(id=record_id)
                
                total_credits = sum(r.course.credits for r in current_credits.select_related('course'))
                
                if total_credits + course_obj.credits > 18:
                    return JsonResponse({
                        'success': False, 
                        'error': f'No puedes asignar esta materia al semestre {semester_taken}. El límite es 18 créditos y alcanzarías {total_credits + course_obj.credits} créditos.'
                    }, status=400)

            # ---------------------------------------------------------
            # VALIDACIÓN DE PRIORIDAD DE REPITENCIA
            # ---------------------------------------------------------
            if course_obj and status != 'PENDING':
                is_retake = AcademicRecord.objects.filter(
                    student=profile, course=course_obj, status='FAILED'
                ).exists()

                if not is_retake:
                    failed_records = AcademicRecord.objects.filter(student=profile, status='FAILED')
                    unresolved_failed = []
                    for f_rec in failed_records:
                        # Check if this failed course is being taken again
                        qs_resolved = AcademicRecord.objects.filter(
                            student=profile, course=f_rec.course,
                            status__in=['IN_PROGRESS', 'PASSED']
                        )
                        if record_id:
                            qs_resolved = qs_resolved.exclude(id=record_id)
                        
                        if not qs_resolved.exists():
                            unresolved_failed.append(f_rec.course.name)
                            
                    if unresolved_failed:
                        return JsonResponse({
                            'success': False,
                            'error': f"Debes matricular primero las materias reprobadas: {', '.join(set(unresolved_failed))}."
                        }, status=400)

            # ---------------------------------------------------------
            # VALIDACIÓN DE PRERREQUISITOS
            # ---------------------------------------------------------
            from django.db.models import Min

            if course_obj:
                # 1. Forward Validation: No puede ver esta materia si no ha pasado los prerrequisitos antes
                if status != 'PENDING':
                    for p in course_obj.course_prerequisites.all():
                        has_passed = AcademicRecord.objects.filter(
                            student=profile,
                            course=p.required_course,
                            status='PASSED',
                            semester_taken__lt=semester_taken
                        ).exists()
                        if not has_passed:
                            return JsonResponse({
                                'success': False, 
                                'error': f'Requiere aprobar "{p.required_course.name}" en un semestre estrictamente anterior a {semester_taken}.'
                            }, status=400)
                
                # 2. Backward Validation: No puede mover/reprobar/eliminar esta materia si es prerrequisito de otra que ya vió
                dependents = course_obj.required_for.all()
                if dependents.exists():
                    for d in dependents:
                        min_dep_sem = AcademicRecord.objects.filter(
                            student=profile,
                            course=d.course
                        ).aggregate(Min('semester_taken'))['semester_taken__min']
                        
                        if min_dep_sem is not None:
                            # Tiene dependiente en min_dep_sem. Debe tener ESTE curso aprobado en semestre < min_dep_sem.
                            other_passed = AcademicRecord.objects.filter(
                                student=profile,
                                course=course_obj,
                                status='PASSED',
                                semester_taken__lt=min_dep_sem
                            )
                            if record_id:
                                other_passed = other_passed.exclude(id=record_id)
                                
                            current_provides = False
                            if status == 'PASSED' and semester_taken < min_dep_sem:
                                current_provides = True
                                
                            if not other_passed.exists() and not current_provides:
                                action_name = "eliminar" if status == 'PENDING' else ("reprobar" if status == 'FAILED' else "mover")
                                return JsonResponse({
                                    'success': False, 
                                    'error': f'No puedes {action_name} esta materia porque afecta a "{d.course.name}" (registrada en semestre {min_dep_sem}).'
                                }, status=400)

            if status == 'PENDING':
                # Si pasa a PENDING, eliminamos el registro para que vuelva al banco de materias
                if record_id:
                    AcademicRecord.objects.filter(id=record_id, student=profile).delete()
                # Ya no borramos por course_id de forma masiva porque el estudiante puede tener
                # múltiples intentos (ej: uno PASSED y uno FAILED) y solo quiere borrar uno.
                return JsonResponse({'success': True})

            # Si hay un record_id, actualizamos ese registro específico
            if record_id:
                record = AcademicRecord.objects.filter(id=record_id, student=profile).first()
                if record:
                    record.status = status
                    record.grade = grade
                    record.semester_taken = semester_taken
                    record.save()
                    return JsonResponse({'success': True})

            # Si no hay record_id pero sí course_id (es decir, viene del banco de materias)
            if course_id:
                course = Course.objects.filter(id=course_id).first()
                if course:
                    AcademicRecord.objects.create(
                        student=profile,
                        course=course,
                        status=status,
                        grade=grade,
                        semester_taken=semester_taken
                    )
                    return JsonResponse({'success': True})

            return JsonResponse({'success': False, 'error': 'Datos insuficientes'}, status=400)

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


