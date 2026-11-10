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


from functools import wraps

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS & SECURITY DECORATORS
# ─────────────────────────────────────────────────────────────────────────────

def student_required(view_func):
    """
    Control de acceso estricto:
      1. Redirige al login si el usuario no está autenticado.
      2. Si el usuario es ADMIN exclusivo (sin perfil de estudiante), redirige al panel admin.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('authentication:login')
        if (request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN') and not hasattr(request.user, 'studentprofile'):
            return redirect('admin_panel:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


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
@student_required
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

    in_progress_records = []
    recent_passed = []
    if profile:
        in_progress_records = (
            AcademicRecord.objects
            .filter(student=profile, status='IN_PROGRESS')
            .select_related('course')
        )
        recent_passed = (
            AcademicRecord.objects
            .filter(student=profile, status='PASSED')
            .select_related('course')
            .order_by('-semester_taken')[:4]
        )

    context = {
        'page_title':               'Mi Dashboard — EduPilot',
        'active_nav':               'dashboard',
        'profile':                  profile,
        'academic_summary':         academic_summary,
        'all_courses_with_status':  all_courses_with_status,
        'in_progress_records':      in_progress_records,
        'recent_passed':            recent_passed,
    }
    return render(request, 'estudiantes/dashboard.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# HISTORIAL ACADÉMICO (TRANSCRIPT)
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@student_required
def student_historial_view(request):
    """
    Kardex / Historial académico completo del estudiante.
    Incluye cálculo de semestre máximo permitido, materias atrasadas y obligatorias.
    """
    profile = _get_student_profile(request)
    academic_summary = _build_academic_summary(profile)

    all_records = []
    sorted_semesters = []
    total_program_credits = 0
    total_program_courses = 0
    max_allowed_semester = 1
    delayed_courses = []       # [{course, delay, is_mandatory, existing_status}]
    mandatory_course_ids = set()

    if profile and profile.program_id:
        from apps.courses.models import Course

        program_courses = (
            Course.objects
            .filter(program=profile.program, is_active=True)
            .order_by('level', 'name')
        )
        total_program_courses = program_courses.count()
        total_program_credits = program_courses.aggregate(Sum('credits'))['credits__sum'] or 120

        # Obtener todos los registros del estudiante
        records = list(
            AcademicRecord.objects
            .filter(student=profile)
            .select_related('course')
            .order_by('semester_taken', 'course__name')
        )
        record_map = {r.course_id: r for r in records}
        passed_course_ids = {r.course_id for r in records if r.status == 'PASSED'}
        in_progress_course_ids = {r.course_id for r in records if r.status == 'IN_PROGRESS'}
        failed_course_ids = {r.course_id for r in records if r.status == 'FAILED'}

        # Mapear intentos por materia para detectar repitencias y materias reprobadas superadas
        attempts_by_course = {}
        for r in records:
            attempts_by_course.setdefault(r.course_id, []).append(r)

        for course_id, rec_list in attempts_by_course.items():
            total_attempts = len(rec_list)
            for idx, r in enumerate(rec_list):
                r.attempt_number = idx + 1
                r.total_attempts = total_attempts
                if r.status == 'FAILED':
                    later_passed = [later for later in rec_list[idx+1:] if later.status == 'PASSED']
                    if later_passed:
                        first_passed = later_passed[0]
                        r.was_retaken_and_passed = True
                        r.retaken_in_semester = first_passed.semester_taken
                        r.retaken_grade = first_passed.grade
                    else:
                        r.was_retaken_and_passed = False
                        later_in_prog = [later for later in rec_list[idx+1:] if later.status == 'IN_PROGRESS']
                        if later_in_prog:
                            r.is_retaking_now = True
                            r.retaking_in_semester = later_in_prog[0].semester_taken
                        else:
                            r.is_unresolved_fail = True
                elif r.status == 'PASSED':
                    earlier_fails = [earlier for earlier in rec_list[:idx] if earlier.status == 'FAILED']
                    if earlier_fails:
                        r.is_retake_success = True
                        r.previous_fail_semesters = [ef.semester_taken for ef in earlier_fails]

        # ── Semestre máximo registrado y próximo permitido ────────────────────
        registered_semesters = sorted(set(r.semester_taken for r in records))
        if registered_semesters:
            # Verificar continuidad: el max registrado continuo desde 1
            max_continuous = 0
            for s in range(1, registered_semesters[-1] + 2):
                if s in registered_semesters:
                    max_continuous = s
                else:
                    break
            max_allowed_semester = max_continuous + 1
        else:
            max_allowed_semester = 1

        # ── Materias atrasadas: fallidas o no cursadas cuyo nivel < max_allowed
        current_sim_sem = max_allowed_semester
        for course in program_courses:
            cid = course.id
            if cid in passed_course_ids or cid in in_progress_course_ids:
                continue  # Ya superada o en curso
            if course.level >= current_sim_sem:
                continue  # No es atrasada, aún no correspondía
            # Está atrasada
            delay = current_sim_sem - course.level
            existing_rec = record_map.get(cid)
            is_mandatory = delay >= 3
            if is_mandatory:
                mandatory_course_ids.add(cid)
            delayed_courses.append({
                'id': cid,
                'code': course.code.strip(),
                'name': course.name.strip(),
                'credits': course.credits,
                'level': course.level,
                'delay': delay,
                'is_mandatory': is_mandatory,
                'existing_status': existing_rec.status if existing_rec else 'PENDING',
                'existing_grade': float(existing_rec.grade) if existing_rec and existing_rec.grade is not None else None,
            })

        # Agrupar registros existentes por semestre tomado
        semesters_dict = {}
        for r in records:
            sem = r.semester_taken
            if sem not in semesters_dict:
                semesters_dict[sem] = []
            semesters_dict[sem].append(r)

        for sem, recs in sorted(semesters_dict.items()):
            graded = [r for r in recs if r.grade is not None]
            avg_sem = sum(r.grade for r in graded) / len(graded) if graded else None
            sem_credits = sum(r.course.credits for r in recs)
            sorted_semesters.append({
                'semester': sem,
                'records': recs,
                'average': round(avg_sem, 2) if avg_sem else None,
                'credits': sem_credits,
                'passed_count': sum(1 for r in recs if r.status == 'PASSED'),
                'failed_count': sum(1 for r in recs if r.status == 'FAILED'),
                'in_progress_count': sum(1 for r in recs if r.status == 'IN_PROGRESS'),
            })

        # Mapear todas las materias del programa para vista completa
        for course in program_courses:
            course_records = attempts_by_course.get(course.id, [])
            rec = course_records[-1] if course_records else None
            has_failed = any(r.status == 'FAILED' for r in course_records)
            is_passed = any(r.status == 'PASSED' for r in course_records)
            all_records.append({
                'course': course,
                'status': rec.status if rec else 'PENDING',
                'grade': rec.grade if rec else None,
                'semester_taken': rec.semester_taken if rec else course.level,
                'attempts': course_records,
                'has_failed': has_failed,
                'is_passed': is_passed,
                'attempts_count': len(course_records),
            })

    program_courses_options = []
    all_program_courses_data = []
    student_records_summary = []
    if profile and profile.program_id:
        from apps.courses.models import Prerequisite
        prereqs = list(
            Prerequisite.objects.filter(
                course__program=profile.program
            ).select_related('required_course')
        )
        prereq_map = {}
        for p in prereqs:
            prereq_map.setdefault(p.course_id, []).append({
                'id': p.required_course_id,
                'code': p.required_course.code.strip(),
                'name': p.required_course.name.strip(),
            })

        all_program_courses_data = [
            {
                'id': c.id,
                'code': c.code.strip(),
                'name': c.name.strip(),
                'credits': c.credits,
                'level': c.level,
                'prerequisites': prereq_map.get(c.id, []),
            }
            for c in program_courses
        ]

        program_courses_options = all_program_courses_data

        student_records_summary = [
            {
                'id': r.id,
                'course_id': r.course_id,
                'course_name': r.course.name.strip(),
                'semester_taken': r.semester_taken,
                'status': r.status,
                'grade': float(r.grade) if r.grade is not None else None,
            }
            for r in records
        ]

    # Agrupar materias del programa por semestre para el modal de registro masivo.
    courses_by_semester = {}
    if profile and profile.program_id:
        existing_record_map = {r.course_id: r for r in (
            AcademicRecord.objects.filter(student=profile).select_related('course')
        )} if profile else {}
        for c in program_courses:
            lvl = c.level
            if lvl not in courses_by_semester:
                courses_by_semester[lvl] = []
            existing_rec = existing_record_map.get(c.id)
            is_delayed = c.id in {d['id'] for d in delayed_courses}
            is_mandatory = c.id in mandatory_course_ids
            courses_by_semester[lvl].append({
                'id': c.id,
                'code': c.code.strip(),
                'name': c.name.strip(),
                'credits': c.credits,
                'level': c.level,
                'existing_status': existing_rec.status if existing_rec else None,
                'existing_grade': float(existing_rec.grade) if existing_rec and existing_rec.grade is not None else None,
                'is_delayed': is_delayed,
                'is_mandatory': is_mandatory,
            })

        # Inyectar materias atrasadas/fallidas en el semestre permitido siguiente
        if delayed_courses and max_allowed_semester not in courses_by_semester:
            courses_by_semester[max_allowed_semester] = []
        for dc in delayed_courses:
            already_in = any(
                c['id'] == dc['id']
                for c in courses_by_semester.get(max_allowed_semester, [])
            )
            if not already_in:
                courses_by_semester.setdefault(max_allowed_semester, []).append({
                    'id': dc['id'],
                    'code': dc['code'],
                    'name': dc['name'],
                    'credits': dc['credits'],
                    'level': dc['level'],
                    'existing_status': dc['existing_status'],
                    'existing_grade': dc['existing_grade'],
                    'is_delayed': True,
                    'is_mandatory': dc['is_mandatory'],
                })

    import json as _json
    courses_by_semester_json = _json.dumps(courses_by_semester)
    all_program_courses_json = _json.dumps(all_program_courses_data)
    student_records_json = _json.dumps(student_records_summary)

    remaining_credits = max(0, total_program_credits - academic_summary['credits_approved'])

    context = {
        'page_title': 'Historial Académico — EduPilot',
        'active_nav': 'historial',
        'profile': profile,
        'academic_summary': academic_summary,
        'sorted_semesters': sorted_semesters,
        'all_records': all_records,
        'program_courses': program_courses_options,
        'semesters_range': list(range(1, 11)),
        'total_program_credits': total_program_credits,
        'total_program_courses': total_program_courses,
        'remaining_credits': remaining_credits,
        'courses_by_semester_json': courses_by_semester_json,
        'all_program_courses_json': all_program_courses_json,
        'student_records_json': student_records_json,
        'max_semester': max(courses_by_semester.keys()) if courses_by_semester else 10,
        'max_allowed_semester': max_allowed_semester,
        'delayed_courses': delayed_courses,
        'mandatory_course_ids': list(mandatory_course_ids),
    }
    return render(request, 'estudiantes/historial.html', context)



# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# HORARIOS Y MATRÍCULA (ESTUDIANTE) — INTEGRACIÓN CON RUTAS Y MOTOR DE HORARIOS
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@student_required
def student_horarios_view(request):
    """
    Vista de planificación, generación de recomendaciones, personalización y guardado
    de horarios para las asignaturas del semestre vigente.
    Se conecta directamente con la ruta académica seleccionada por el estudiante.
    """
    import json
    from services.route_generator import RouteGeneratorService, Strategy
    from services.schedule_engine import ScheduleEngine, DAYS_ORDER
    from apps.routes.services.saved_route_service import SavedRouteService
    from apps.routes.services.saved_schedule_service import SavedScheduleService
    from apps.ai.services.ai_service import ai_service
    from apps.courses.models import Course

    profile = _get_student_profile(request)
    academic_summary = _build_academic_summary(profile)

    # 1. Obtener rutas guardadas del estudiante
    saved_routes = list(SavedRouteService.get_student_routes(profile)) if profile else []

    selected_route = None
    route_id_param = request.GET.get('route_id')
    if route_id_param and profile:
        try:
            selected_route = SavedRouteService.get_route_for_student(profile, int(route_id_param))
        except Exception:
            selected_route = None

    if not selected_route and saved_routes:
        selected_route = next((r for r in saved_routes if r.is_favorite), saved_routes[0])

    # 2. Determinar las materias del semestre vigente
    current_courses = []
    route_source_name = "Plan estándar sugerido"

    if selected_route:
        current_courses = SavedRouteService.get_semester_courses(selected_route, semester_index=1)
        route_source_name = selected_route.name
    elif profile and profile.program_id:
        # Si no ha guardado una ruta aún, generar la ruta equilibrada en memoria para no bloquear al estudiante
        active_route = RouteGeneratorService.generate(profile=profile, strategy=Strategy.BALANCED)
        if active_route.semesters:
            current_courses = active_route.semesters[0].courses
            route_source_name = f"Ruta Recomendada ({active_route.strategy_label})"

    # 3. Consultar catálogo completo de grupos de estas materias
    groups_catalog = ScheduleEngine.get_course_groups_catalog(current_courses) if current_courses else {}

    # Serializar catálogo para el selector interactivo de grupos (desplegable)
    catalog_json = {}
    for cid, grp_list in groups_catalog.items():
        catalog_json[cid] = [
            {
                'course_id': g.course_id,
                'course_code': g.course_code,
                'course_name': g.course_name,
                'group_number': g.group_number,
                'available_spots': g.available_spots,
                'summary': g.schedule_summary,
                'sessions': [
                    {
                        'day': s.day,
                        'start_time': s.start_time.strftime('%H:%M') if s.start_time else '--:--',
                        'end_time': s.end_time.strftime('%H:%M') if s.end_time else '--:--',
                        'classroom': s.classroom,
                    }
                    for s in g.sessions
                ]
            }
            for g in grp_list
        ]

    # 4. Generar recomendaciones de horarios automáticas
    proposals = ScheduleEngine.generate_recommendations(current_courses) if current_courses else []
    active_proposal = proposals[0] if proposals else None

    # 5. Obtener horarios ya guardados por el estudiante
    saved_schedules = list(SavedScheduleService.get_student_schedules(profile)) if profile else []

    # Configuración de matriz de calendario semanal
    schedule_days = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
    hours_grid = [
        '07:00 - 08:00',
        '08:00 - 09:00',
        '09:00 - 10:00',
        '10:00 - 11:00',
        '11:00 - 12:00',
        '12:00 - 13:00',
        '13:00 - 14:00',
        '14:00 - 15:00',
        '15:00 - 16:00',
        '16:00 - 17:00',
        '17:00 - 18:00',
        '18:00 - 19:00',
        '19:00 - 20:00',
    ]

    context = {
        'page_title': 'Matrícula y Horarios — EduPilot',
        'active_nav': 'horarios',
        'profile': profile,
        'academic_summary': academic_summary,
        'saved_routes': saved_routes,
        'selected_route': selected_route,
        'route_source_name': route_source_name,
        'current_courses': current_courses,
        'proposals': proposals,
        'active_proposal': active_proposal,
        'saved_schedules': saved_schedules,
        'catalog_json_str': json.dumps(catalog_json),
        'schedule_days': schedule_days,
        'hours_grid': hours_grid,
        'ai_model_label': ai_service.current_model_name,
    }
    return render(request, 'estudiantes/horarios.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# MIS PLANES Y HORARIOS GUARDADOS
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@student_required
def student_guardados_view(request):
    """
    Panel centralizado de rutas académicas y horarios guardados en base de datos.
    Permite consultar, comparar, seleccionar favoritos y eliminar registros propios.
    """
    from apps.routes.services.saved_route_service import SavedRouteService
    from apps.routes.services.saved_schedule_service import SavedScheduleService

    profile = _get_student_profile(request)
    academic_summary = _build_academic_summary(profile)

    saved_routes = list(SavedRouteService.get_student_routes(profile)) if profile else []
    saved_schedules = list(SavedScheduleService.get_student_schedules(profile)) if profile else []
    active_route = SavedRouteService.get_active_or_default_route(profile) if profile else None

    # Verificar si hubo cambios en la oferta para los horarios guardados
    schedules_with_status = []
    for sch in saved_schedules:
        drift = SavedScheduleService.check_offer_changes(sch)
        schedules_with_status.append({
            'schedule': sch,
            'drift': drift,
        })

    context = {
        'page_title': 'Mis Planes y Horarios Guardados — EduPilot',
        'active_nav': 'guardados',
        'profile': profile,
        'academic_summary': academic_summary,
        'saved_routes': saved_routes,
        'active_route': active_route,
        'total_plans': len(saved_routes),
        'schedules_with_status': schedules_with_status,
        'total_schedules': len(saved_schedules),
    }
    return render(request, 'estudiantes/guardados.html', context)



# ─────────────────────────────────────────────────────────────────────────────
# MATERIAS DEL ESTUDIANTE
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@student_required
def student_courses_view(request):
    """
    Vista de materias y plan de estudios del estudiante.
    Calcula en tiempo real con datos de la BD:
      - KPIs globales del plan (total materias, aprobadas, pendientes, créditos restantes).
      - Catálogo completo de asignaturas del programa con prerrequisitos reales y su estado de cumplimiento.
      - Estado académico individual (Aprobada con nota, En curso, Habilitada para cursar, Bloqueada por prerrequisito).
      - Dependencias directas (materias que requieren cada asignatura).
      - Datos agrupados para la Malla Curricular por semestres (1 a N).
      - Estructura JSON serializada para reactividad completa en el frontend (búsqueda, filtros, drawer, vistas).
    """
    import json
    from apps.courses.models import Course, Prerequisite, CourseGroup

    profile = _get_student_profile(request)
    academic_summary = _build_academic_summary(profile)

    courses_list = []
    semesters_list = []
    semesters_levels = []
    distinct_credits = []
    selected_course_id = request.GET.get('selected_course', '').strip()

    # KPIs por defecto
    total_courses_count = 0
    total_credits_count = 0
    courses_passed_count = 0
    credits_approved_count = 0
    passed_pct = 0
    courses_pending_count = 0
    courses_in_progress_count = 0
    credits_in_progress_count = 0
    credits_remaining = 0
    estimated_semesters = 0

    if profile and profile.program_id:
        program = profile.program
        program_courses = (
            Course.objects
            .filter(program=program, is_active=True)
            .order_by('level', 'name')
        )
        total_courses_count = program_courses.count()
        total_credits_count = sum(c.credits for c in program_courses)

        # Registros del estudiante
        records = list(
            AcademicRecord.objects
            .filter(student=profile)
            .select_related('course')
            .order_by('semester_taken', 'id')
        )

        # Mapa de estado preferente y notas: PASSED > IN_PROGRESS > FAILED
        status_rank = {'PASSED': 3, 'IN_PROGRESS': 2, 'FAILED': 1}
        course_record_map = {}
        for r in records:
            cid = r.course_id
            if cid not in course_record_map:
                course_record_map[cid] = r
            else:
                existing = course_record_map[cid]
                if status_rank.get(r.status, 0) >= status_rank.get(existing.status, 0):
                    course_record_map[cid] = r

        passed_course_ids = {cid for cid, r in course_record_map.items() if r.status == 'PASSED'}
        in_progress_course_ids = {cid for cid, r in course_record_map.items() if r.status == 'IN_PROGRESS'}
        failed_course_ids = {cid for cid, r in course_record_map.items() if r.status == 'FAILED'}

        # Prerrequisitos y materias dependientes
        all_prereqs = list(
            Prerequisite.objects
            .filter(course__in=program_courses)
            .select_related('course', 'required_course')
        )

        prereqs_by_course = {}
        for p in all_prereqs:
            prereqs_by_course.setdefault(p.course_id, []).append(p.required_course)

        dependents_by_course = {}
        for p in all_prereqs:
            dependents_by_course.setdefault(p.required_course_id, []).append(p.course)

        # Campos de aprendizaje / tipología
        learning_field_map = {}
        course_groups = CourseGroup.objects.filter(course__in=program_courses).values('course_id', 'learning_field')
        for cg in course_groups:
            if cg['course_id'] and cg['learning_field']:
                learning_field_map[cg['course_id']] = cg['learning_field']

        # Construcción detallada de cada materia
        for course in program_courses:
            cid = course.id
            code_clean = course.code.strip() if course.code else f"MAT-{course.id}"
            name_clean = course.name.strip()

            # Tipología
            if cid in learning_field_map and learning_field_map[cid]:
                typology = learning_field_map[cid].title()
            elif course.level <= 2:
                typology = 'Ciencias Básicas'
            elif course.level <= 5:
                typology = 'Troncal Fundamental'
            elif course.level <= 7:
                typology = 'Troncal Avanzada'
            else:
                typology = 'Énfasis y Titulación'

            department = 'Facultad de Ingeniería'

            # Prerrequisitos de esta materia
            req_courses = prereqs_by_course.get(cid, [])
            prereqs_data = []
            pending_prereq_names = []
            for req in req_courses:
                req_cid = req.id
                req_rec = course_record_map.get(req_cid)
                if req_cid in passed_course_ids:
                    p_status = 'PASSED'
                    p_label = f"Aprobada{f' ({req_rec.grade:.1f})' if req_rec and req_rec.grade is not None else ''}"
                elif req_cid in in_progress_course_ids:
                    p_status = 'IN_PROGRESS'
                    p_label = 'En curso'
                    pending_prereq_names.append(f"{req.code.strip()} ({req.name.strip()})")
                elif req_cid in failed_course_ids:
                    p_status = 'FAILED'
                    p_label = f"Reprobada{f' ({req_rec.grade:.1f})' if req_rec and req_rec.grade is not None else ''}"
                    pending_prereq_names.append(f"{req.code.strip()} ({req.name.strip()})")
                else:
                    p_status = 'PENDING'
                    p_label = 'No cursada'
                    pending_prereq_names.append(f"{req.code.strip()} ({req.name.strip()})")

                prereqs_data.append({
                    'id': req.id,
                    'code': req.code.strip(),
                    'name': req.name.strip(),
                    'level': req.level,
                    'status': p_status,
                    'label': p_label,
                })

            has_prereqs = len(prereqs_data) > 0
            pending_prereqs_count = len(pending_prereq_names)
            all_prereqs_passed = (pending_prereqs_count == 0)

            # Estado académico de la materia para este estudiante
            rec = course_record_map.get(cid)
            if cid in passed_course_ids:
                status_code = 'PASSED'
                status_label = 'Aprobada'
                grade_val = rec.grade if rec else None
                grade_str = f"{grade_val:.1f}" if grade_val is not None else "4.0"
                badge_text = f"Aprobada (Nota: {grade_str})"
                badge_color = 'emerald'
                advice = f"Has superado satisfactoriamente esta materia con una calificación de {grade_str}. Los {course.credits} créditos se encuentran acumulados para tu titulación."
            elif cid in in_progress_course_ids:
                status_code = 'IN_PROGRESS'
                status_label = 'En curso'
                sem_str = f"Sem. {rec.semester_taken}" if rec and rec.semester_taken else f"Sem. {profile.current_semester}"
                badge_text = f"En curso ({sem_str})"
                badge_color = 'cyan'
                grade_val = None
                advice = f"Estás cursando esta materia en el periodo actual. Recuerda mantener un promedio superior a 3.0 para asegurar la aprobación y desbloquear asignaturas posteriores."
            elif cid in failed_course_ids:
                status_code = 'FAILED'
                status_label = 'Reprobada'
                grade_val = rec.grade if rec else None
                grade_str = f"{grade_val:.1f}" if grade_val is not None else "2.0"
                badge_text = f"Reprobada (Nota: {grade_str})"
                badge_color = 'rose'
                advice = f"Esta materia fue reprobada previamente con nota {grade_str}. Debe ser matriculada con prioridad de repitencia en tu próximo periodo para desbloquear las materias dependientes."
            else:
                grade_val = None
                if all_prereqs_passed:
                    status_code = 'AVAILABLE'
                    status_label = 'Habilitada para cursar'
                    badge_text = 'Habilitada para cursar'
                    badge_color = 'sky'
                    advice = f"Cumples con el 100% de los prerrequisitos requeridos. Tienes luz verde para matricular esta asignatura en tu próxima planificación académica."
                else:
                    status_code = 'BLOCKED'
                    status_label = 'Bloqueada por prerrequisito'
                    badge_text = 'Bloqueada por prerrequisito'
                    badge_color = 'amber'
                    advice = f"Podrás inscribir esta asignatura una vez apruebes los prerrequisitos pendientes: {', '.join(pending_prereq_names[:3])}."

            # Materias dependientes
            dependents_data = []
            for dep in dependents_by_course.get(cid, []):
                dependents_data.append({
                    'id': dep.id,
                    'code': dep.code.strip(),
                    'name': dep.name.strip(),
                    'level': dep.level,
                })

            description = course.description.strip() if course.description else (
                f"Asignatura teórica y práctica correspondiente al semestre {course.level} del programa de {program.name}. "
                f"Desarrolla competencias fundamentales del perfil profesional y aporta {course.credits} créditos al plan de estudios."
            )

            course_item = {
                'id': course.id,
                'code': code_clean,
                'name': name_clean,
                'credits': course.credits,
                'level': course.level,
                'typology': typology,
                'department': department,
                'description': description,
                'status_code': status_code,
                'status_label': status_label,
                'badge_text': badge_text,
                'badge_color': badge_color,
                'grade': grade_val,
                'has_prereqs': has_prereqs,
                'prerequisites': prereqs_data,
                'pending_prereqs_count': pending_prereqs_count,
                'dependents': dependents_data,
                'advice': advice,
            }
            courses_list.append(course_item)

        # Distinct levels and credits for filters
        semesters_levels = sorted(list(set(c['level'] for c in courses_list)))
        distinct_credits = sorted(list(set(c['credits'] for c in courses_list)))

        # KPIs calculations
        courses_passed_count = sum(1 for c in courses_list if c['status_code'] == 'PASSED')
        credits_approved_count = sum(c['credits'] for c in courses_list if c['status_code'] == 'PASSED')
        passed_pct = round((credits_approved_count / total_credits_count * 100)) if total_credits_count > 0 else 0

        courses_in_progress_count = sum(1 for c in courses_list if c['status_code'] == 'IN_PROGRESS')
        credits_in_progress_count = sum(c['credits'] for c in courses_list if c['status_code'] == 'IN_PROGRESS')

        courses_pending_count = total_courses_count - courses_passed_count - courses_in_progress_count
        credits_remaining = max(0, total_credits_count - credits_approved_count)
        estimated_semesters = max(1, round(credits_remaining / 16)) if credits_remaining > 0 else 0

        # Semesters data for Malla Curricular
        for lvl in semesters_levels:
            sem_courses = [c for c in courses_list if c['level'] == lvl]
            sem_passed = sum(1 for c in sem_courses if c['status_code'] == 'PASSED')
            sem_in_progress = sum(1 for c in sem_courses if c['status_code'] == 'IN_PROGRESS')
            sem_credits = sum(c['credits'] for c in sem_courses)
            is_completed = (sem_passed == len(sem_courses) and len(sem_courses) > 0)
            is_current = (lvl == profile.current_semester or sem_in_progress > 0)
            is_next = (lvl == profile.current_semester + 1)

            if is_completed:
                status_text = '100% Aprobado'
                badge_type = 'completed'
            elif sem_in_progress > 0:
                status_text = f"{sem_in_progress} en curso"
                badge_type = 'current'
            elif is_next:
                status_text = 'Siguiente periodo'
                badge_type = 'next'
            else:
                status_text = 'Pendiente'
                badge_type = 'pending'

            semesters_list.append({
                'level': lvl,
                'courses': sem_courses,
                'total_courses': len(sem_courses),
                'total_credits': sem_credits,
                'passed_count': sem_passed,
                'in_progress_count': sem_in_progress,
                'is_completed': is_completed,
                'is_current': is_current,
                'is_next': is_next,
                'status_text': status_text,
                'badge_type': badge_type,
            })

    kpis = {
        'total_courses': total_courses_count,
        'total_credits': total_credits_count,
        'courses_passed': courses_passed_count,
        'credits_approved': credits_approved_count,
        'passed_pct': passed_pct,
        'courses_pending': courses_pending_count,
        'courses_in_progress': courses_in_progress_count,
        'credits_in_progress': credits_in_progress_count,
        'credits_remaining': credits_remaining,
        'estimated_semesters': estimated_semesters,
    }

    # Serializar a JSON para reactividad instantánea en el frontend
    courses_json = json.dumps(courses_list)

    context = {
        'page_title': 'Mis Materias — EduPilot',
        'active_nav': 'courses',
        'profile': profile,
        'academic_summary': academic_summary,
        'kpis': kpis,
        'courses': courses_list,
        'courses_json': courses_json,
        'semesters_levels': semesters_levels,
        'distinct_credits': distinct_credits,
        'semesters_list': semesters_list,
        'selected_course_id': selected_course_id,
    }
    return render(request, 'estudiantes/materias.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# RUTAS ACADÉMICAS — GENERACIÓN MULTI-ALTERNATIVA Y COMPARACIÓN
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@student_required
def student_routes_view(request):
    """
    Vista de rutas académicas con generación de hasta 3 alternativas fundamentadas:
      - Avance Acelerado (FAST_TRACK)
      - Distribución Equilibrada (BALANCED)
      - Planificación Flexible (LIGHT)
    Permite comparar métricas, verificar cumplimiento del margen ideal de 10 semestres,
    leer el análisis de IA y guardar alternativas seleccionadas.
    """
    from services.route_generator import RouteGeneratorService, Strategy
    from apps.routes.services.saved_route_service import SavedRouteService
    from apps.ai.services.ai_service import ai_service

    profile = _get_student_profile(request)
    academic_summary = _build_academic_summary(profile)

    # 1. Generar alternativas deduplicadas para el perfil
    alternatives = RouteGeneratorService.generate_alternatives(profile) if profile else []

    # 2. Identificar la estrategia seleccionada activa
    strategy_param = request.GET.get('strategy', Strategy.BALANCED).upper()
    active_route = next((r for r in alternatives if r.strategy == strategy_param), None)
    if not active_route and alternatives:
        active_route = alternatives[0]
        strategy_param = active_route.strategy

    # 3. Comprobar si el estudiante ya tiene rutas guardadas
    saved_routes_count = SavedRouteService.get_student_routes(profile).count() if profile else 0

    context = {
        'page_title':      'Rutas Académicas — EduPilot',
        'active_nav':      'routes',
        'profile':         profile,
        'academic_summary': academic_summary,
        'route':           active_route,
        'strategy':        strategy_param,
        'alternatives':    alternatives,
        'all_strategies':  [
            (key, Strategy.LABELS[key]) for key in Strategy.ALL
        ],
        'saved_routes_count': saved_routes_count,
        'ai_model_label':  ai_service.current_model_name,
    }
    return render(request, 'estudiantes/rutas.html', context)


@never_cache
@student_required
def save_route_view(request):
    """
    Endpoint para persistir una ruta generada en la base de datos.
    Soporta peticiones POST ordinarias y AJAX (JSON).
    """
    from services.route_generator import RouteGeneratorService, Strategy
    from apps.routes.services.saved_route_service import SavedRouteService

    if request.method != 'POST':
        return redirect('student:routes')

    profile = _get_student_profile(request)
    if not profile:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'No se encontró el perfil de estudiante.'}, status=400)
        messages.error(request, 'No se encontró el perfil de estudiante.')
        return redirect('student:routes')

    strategy = request.POST.get('strategy', Strategy.BALANCED).upper()
    custom_name = request.POST.get('name', '').strip()
    is_favorite = request.POST.get('is_favorite') in ['true', '1', 'on']

    route_result = RouteGeneratorService.generate(profile=profile, strategy=strategy)
    if route_result.is_empty or route_result.error:
        err_msg = route_result.error or 'No fue posible guardar una ruta sin materias.'
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect('student:routes')

    saved_route = SavedRouteService.save_route(
        student=profile,
        route_result=route_result,
        name=custom_name or f"Ruta {route_result.strategy_label}",
        is_favorite=is_favorite
    )

    success_msg = f"✓ Ruta '{saved_route.name}' guardada exitosamente en tus planes."
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': success_msg,
            'route_id': saved_route.id,
            'name': saved_route.name
        })

    messages.success(request, success_msg)
    return redirect('student:guardados')


@never_cache
@student_required
def set_favorite_route_view(request, route_id):
    """Establece una ruta propia como favorita."""
    from apps.routes.services.saved_route_service import SavedRouteService
    profile = _get_student_profile(request)
    if profile:
        try:
            SavedRouteService.set_favorite(profile, route_id)
            messages.success(request, "Ruta principal actualizada correctamente.")
        except Exception as e:
            messages.error(request, str(e))
    return redirect('student:guardados')


@never_cache
@student_required
def delete_route_view(request, route_id):
    """Elimina una ruta propia garantizando control de acceso."""
    from apps.routes.services.saved_route_service import SavedRouteService
    profile = _get_student_profile(request)
    if profile:
        try:
            SavedRouteService.delete_route(profile, route_id)
            messages.success(request, "Ruta eliminada de tus planes guardados.")
        except Exception as e:
            messages.error(request, str(e))
    return redirect('student:guardados')


@never_cache
@student_required
def route_ai_explanation_view(request):
    """
    Endpoint AJAX para solicitar la explicación de IA de una ruta académica de forma asíncrona.
    No bloquea la carga de la página ni la interacción del usuario.
    """
    from services.route_generator import RouteGeneratorService, Strategy
    from apps.ai.services.ai_service import ai_service

    profile = _get_student_profile(request)
    if not profile:
        return JsonResponse({'success': False, 'error': 'No autenticado.'}, status=401)

    strategy = request.GET.get('strategy') or request.POST.get('strategy') or Strategy.BALANCED
    route_result = RouteGeneratorService.generate(profile=profile, strategy=strategy.upper())

    explanation = ai_service.explain_route(profile=profile, route=route_result)

    return JsonResponse({
        'success': True,
        'explanation': explanation,
        'model_name': ai_service.current_model_name,
        'strategy': route_result.strategy_label,
    })


# ─────────────────────────────────────────────────────────────────────────────
# HORARIOS — ENDPOINTS DE ACCIÓN, VALIDACIÓN AJAX Y PERSISTENCIA
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@student_required
def validate_schedule_view(request):
    """
    Endpoint AJAX POST para revalidar inmediatamente una combinación horaria
    cuando el estudiante cambia o selecciona grupos manualmente.
    """
    import json
    from services.schedule_engine import ScheduleEngine, CourseGroupOption
    from apps.courses.models import Course, CourseGroup

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)

    try:
        body = json.loads(request.body.decode('utf-8'))
        selected_groups_data = body.get('groups', [])  # list of {course_id, group_number}
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'JSON malformado: {e}'}, status=400)

    course_ids = [item.get('course_id') for item in selected_groups_data if item.get('course_id')]
    courses = list(Course.objects.filter(id__in=course_ids))
    catalog = ScheduleEngine.get_course_groups_catalog(courses)

    selected_group_options = []
    for item in selected_groups_data:
        cid = int(item.get('course_id', 0))
        grp_num = str(item.get('group_number', '')).strip()
        options = catalog.get(cid, [])
        match = next((opt for opt in options if opt.group_number == grp_num), None)
        if match:
            selected_group_options.append(match)

    proposal = ScheduleEngine.validate_custom_combination(selected_group_options)

    return JsonResponse({
        'success': True,
        'is_valid': proposal.is_valid,
        'conflicts': proposal.conflicts,
        'metrics': {
            'quality_score': proposal.metrics.quality_score,
            'total_class_hours': proposal.metrics.total_class_hours,
            'total_weekly_wait_minutes': proposal.metrics.total_weekly_wait_minutes,
            'days_with_class': proposal.metrics.days_with_class,
            'days_list': proposal.metrics.days_list,
            'earliest_start': proposal.metrics.earliest_start,
            'latest_end': proposal.metrics.latest_end,
            'longest_daily_stay_hours': proposal.metrics.longest_daily_stay_hours,
            'hours_per_day': proposal.metrics.hours_per_day,
            'warnings': proposal.metrics.warnings,
            'total_credits': proposal.total_credits,
            'courses_count': proposal.courses_count,
        }
    })


@never_cache
@student_required
def save_schedule_view(request):
    """
    Endpoint para persistir un horario semestral validado en la base de datos.
    """
    import json
    from services.schedule_engine import ScheduleEngine
    from apps.routes.models import SavedRoute
    from apps.routes.services.saved_schedule_service import SavedScheduleService
    from apps.courses.models import Course

    if request.method != 'POST':
        return redirect('student:horarios')

    profile = _get_student_profile(request)
    if not profile:
        return JsonResponse({'success': False, 'error': 'No autenticado.'}, status=401)

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8'))
        else:
            data = request.POST

        name = data.get('name', 'Mi Horario Semestral').strip() or 'Mi Horario Semestral'
        route_id = data.get('route_id')
        groups_raw = data.get('groups')
        if isinstance(groups_raw, str):
            groups_data = json.loads(groups_raw)
        else:
            groups_data = groups_raw or []
    except Exception as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': f'Datos inválidos: {e}'}, status=400)
        messages.error(request, 'Datos de horario inválidos.')
        return redirect('student:horarios')

    # Reconstruir opciones
    course_ids = [int(item['course_id']) for item in groups_data if item.get('course_id')]
    courses = list(Course.objects.filter(id__in=course_ids))
    catalog = ScheduleEngine.get_course_groups_catalog(courses)

    selected_group_options = []
    for item in groups_data:
        cid = int(item['course_id'])
        grp_num = str(item['group_number']).strip()
        options = catalog.get(cid, [])
        match = next((opt for opt in options if opt.group_number == grp_num), None)
        if match:
            selected_group_options.append(match)

    proposal = ScheduleEngine.validate_custom_combination(selected_group_options)

    if not proposal.is_valid:
        err_msg = "No se puede guardar un horario con solapamientos o cruces entre clases."
        if is_ajax:
            return JsonResponse({'success': False, 'error': err_msg, 'conflicts': proposal.conflicts}, status=400)
        messages.error(request, err_msg)
        return redirect('student:horarios')

    saved_route = None
    if route_id:
        try:
            saved_route = SavedRoute.objects.filter(id=int(route_id), student=profile).first()
        except Exception:
            saved_route = None

    saved_schedule = SavedScheduleService.save_proposal(
        student=profile,
        proposal=proposal,
        name=name,
        saved_route=saved_route
    )

    success_msg = f"✓ Horario '{saved_schedule.name}' guardado exitosamente."
    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': success_msg,
            'schedule_id': saved_schedule.id,
            'name': saved_schedule.name
        })

    messages.success(request, success_msg)
    return redirect('student:guardados')


@never_cache
@student_required
def delete_schedule_view(request, schedule_id):
    """Elimina un horario guardado propio."""
    from apps.routes.services.saved_schedule_service import SavedScheduleService
    profile = _get_student_profile(request)
    if profile:
        try:
            SavedScheduleService.delete_schedule(profile, schedule_id)
            messages.success(request, "Horario eliminado correctamente.")
        except Exception as e:
            messages.error(request, str(e))
    return redirect('student:guardados')


@never_cache
@student_required
def schedule_ai_explanation_view(request):
    """
    Endpoint AJAX para solicitar la explicación de IA del horario activo en pantalla.
    """
    import json
    from services.schedule_engine import ScheduleEngine
    from apps.ai.services.ai_service import ai_service
    from apps.courses.models import Course

    profile = _get_student_profile(request)
    if not profile:
        return JsonResponse({'success': False, 'error': 'No autenticado.'}, status=401)

    try:
        if request.method == 'POST':
            body = json.loads(request.body.decode('utf-8'))
            groups_data = body.get('groups', [])
        else:
            groups_raw = request.GET.get('groups', '[]')
            groups_data = json.loads(groups_raw)
    except Exception:
        groups_data = []

    course_ids = [int(item['course_id']) for item in groups_data if item.get('course_id')]
    courses = list(Course.objects.filter(id__in=course_ids))
    catalog = ScheduleEngine.get_course_groups_catalog(courses)

    selected_group_options = []
    for item in groups_data:
        cid = int(item['course_id'])
        grp_num = str(item['group_number']).strip()
        options = catalog.get(cid, [])
        match = next((opt for opt in options if opt.group_number == grp_num), None)
        if match:
            selected_group_options.append(match)

    proposal = ScheduleEngine.validate_custom_combination(selected_group_options)
    explanation = ai_service.explain_schedule(profile=profile, proposal=proposal)

    return JsonResponse({
        'success': True,
        'explanation': explanation,
        'model_name': ai_service.current_model_name,
        'quality_score': proposal.metrics.quality_score,
    })



# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE HISTORIAL ACADÉMICO (AUTOFILL Y UPDATE)
# ─────────────────────────────────────────────────────────────────────────────
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
import json

@student_required
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
    next_url = request.POST.get('next') or request.GET.get('next') or 'student:historial'
    return redirect(next_url)


@student_required
def save_academic_record_view(request):
    """
    Guarda (crea o actualiza) un registro académico del estudiante desde el Historial.
    Soporta POST tradicional (con redirección y messages) y AJAX (JsonResponse).
    """
    if request.method != 'POST':
        return redirect('student:historial')

    profile = _get_student_profile(request)
    if not profile:
        messages.error(request, 'No se encontró el perfil de estudiante.')
        return redirect('student:historial')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.content_type

    try:
        if 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST

        record_id = data.get('record_id')
        course_id = data.get('course_id')
        semester_taken_raw = data.get('semester_taken')
        status = (data.get('status') or 'PASSED').strip().upper()
        grade_raw = data.get('grade')

        from apps.courses.models import Course
        from apps.academic.models import AcademicRecord
        from django.core.exceptions import ValidationError

        # Validar semestre
        try:
            semester_taken = int(semester_taken_raw) if semester_taken_raw else profile.current_semester
        except (ValueError, TypeError):
            semester_taken = profile.current_semester

        # Validar nota
        grade = None
        if grade_raw is not None and str(grade_raw).strip() != '':
            try:
                grade = float(grade_raw)
                if grade < 0.0 or grade > 5.0:
                    raise ValidationError('La calificación debe estar entre 0.0 y 5.0.')
            except ValueError:
                raise ValidationError('Formato de calificación inválido. Usa números decimales (ej. 4.2).')

        # Ajuste automático de estado según nota (regla: >= 3.0 aprueba, < 3.0 reprueba)
        if status == 'IN_PROGRESS':
            grade = None
        else:
            if grade is not None:
                status = 'PASSED' if grade >= 3.0 else 'FAILED'
            elif status == 'PASSED':
                grade = 3.5
            elif status == 'FAILED':
                grade = 2.0

        # Obtener o validar curso
        course = None
        if course_id:
            course = Course.objects.filter(id=course_id).first()
        elif record_id:
            rec_existing = AcademicRecord.objects.filter(id=record_id, student=profile).first()
            if rec_existing:
                course = rec_existing.course

        if not course:
            raise ValidationError('Debes seleccionar una materia válida.')

        # ── Validación de registro progresivo ─────────────────────────────────
        # Si es un nuevo registro (no edición), verificar que no salte semestres
        if not record_id:
            existing_records = AcademicRecord.objects.filter(student=profile)
            registered_sems = sorted(set(r.semester_taken for r in existing_records))
            if registered_sems:
                max_continuous = 0
                for s in range(1, registered_sems[-1] + 2):
                    if s in registered_sems:
                        max_continuous = s
                    else:
                        break
                max_allowed = max_continuous + 1
            else:
                max_allowed = 1

            if semester_taken > max_allowed:
                raise ValidationError(
                    f'Registro progresivo requerido. Solo puedes registrar hasta el Semestre {max_allowed}. '
                    f'Primero debes registrar el Semestre {max_allowed}.'
                )

        # ── Validación de límite de 18 créditos por semestre ─────────────────
        # Créditos ya registrados en el semestre destino (excluir el registro actual si es edición)
        sem_records_qs = AcademicRecord.objects.filter(student=profile, semester_taken=semester_taken)
        if record_id:
            sem_records_qs = sem_records_qs.exclude(id=record_id)
        credits_in_sem = sum(r.course.credits for r in sem_records_qs.select_related('course'))
        if course.credits > 0 and credits_in_sem + course.credits > 18:
            raise ValidationError(
                f'Límite de créditos superado. El semestre {semester_taken} ya tiene {credits_in_sem} créditos. '
                f'Agregar "{course.name}" ({course.credits} cr) excede el máximo de 18 créditos por semestre.'
            )

        # ── Validación de materias ya aprobadas previamente ───────────────────
        passed_other = AcademicRecord.objects.filter(
            student=profile, course=course, status='PASSED'
        )
        if record_id:
            passed_other = passed_other.exclude(id=record_id)
        else:
            passed_other = passed_other.exclude(semester_taken=semester_taken)

        if passed_other.exists():
            prev_p = passed_other.first()
            raise ValidationError(
                f'La materia "{course.name}" ya fue aprobada en el Semestre {prev_p.semester_taken} '
                f'(calificación {prev_p.grade}). No puedes volver a registrar una asignatura ya superada.'
            )

        # ── Validación estricta de prerrequisitos ─────────────────────────────
        from apps.courses.models import Prerequisite
        course_prereqs = Prerequisite.objects.filter(course=course).select_related('required_course')
        unmet_reqs = []
        for pr in course_prereqs:
            req_c = pr.required_course
            has_passed = AcademicRecord.objects.filter(
                student=profile,
                course=req_c,
                semester_taken__lt=semester_taken,
                status='PASSED'
            ).exists()
            if not has_passed:
                unmet_reqs.append(req_c.name.strip())

        if unmet_reqs:
            reqs_str = ', '.join(f'"{name}"' for name in unmet_reqs)
            raise ValidationError(
                f'No puedes registrar "{course.name}" en el Semestre {semester_taken}: '
                f'requiere haber aprobado previamente los prerrequisitos: {reqs_str}.'
            )

        # Si viene record_id, actualizar
        if record_id:
            record = AcademicRecord.objects.filter(id=record_id, student=profile).first()
            if not record:
                raise ValidationError('El registro académico no existe o no tienes permiso para editarlo.')
            record.course = course
            record.semester_taken = semester_taken
            record.status = status
            record.grade = grade
            record.full_clean()
            record.save()
            msg = f'Materia "{course.name}" actualizada en el historial correctamente.'
        else:
            # Si no hay record_id, buscar si ya existe para este curso EN ESTE SEMESTRE ESPECÍFICO
            existing = AcademicRecord.objects.filter(
                student=profile, course=course, semester_taken=semester_taken
            ).first()
            if existing:
                existing.status = status
                existing.grade = grade
                existing.full_clean()
                existing.save()
                msg = f'Registro de "{course.name}" actualizado en el Semestre {semester_taken}.'
            else:
                record = AcademicRecord(
                    student=profile,
                    course=course,
                    semester_taken=semester_taken,
                    status=status,
                    grade=grade
                )
                record.full_clean()
                record.save()
                msg = f'Materia "{course.name}" registrada exitosamente en el Semestre {semester_taken}.'

        if is_ajax:
            return JsonResponse({'success': True, 'message': msg})

        messages.success(request, msg)
        return redirect('student:historial')

    except ValidationError as e:
        err_msg = '; '.join(e.messages) if hasattr(e, 'messages') else str(e)
        if is_ajax:
            return JsonResponse({'success': False, 'error': err_msg}, status=400)
        messages.error(request, f'Error al registrar materia: {err_msg}')
        return redirect('student:historial')
    except Exception as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, f'Error inesperado: {str(e)}')
        return redirect('student:historial')


@student_required
def delete_academic_record_view(request):
    """
    Elimina un registro académico del historial del estudiante.
    """
    if request.method != 'POST':
        return redirect('student:historial')

    profile = _get_student_profile(request)
    if not profile:
        messages.error(request, 'No se encontró el perfil de estudiante.')
        return redirect('student:historial')

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.content_type

    try:
        if 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST

        record_id = data.get('record_id')
        from apps.academic.models import AcademicRecord

        record = AcademicRecord.objects.filter(id=record_id, student=profile).first()
        if not record:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'Registro no encontrado.'}, status=404)
            messages.error(request, 'El registro no fue encontrado.')
            return redirect('student:historial')

        course_name = record.course.name
        record.delete()
        msg = f'Registro de "{course_name}" eliminado del historial.'

        if is_ajax:
            return JsonResponse({'success': True, 'message': msg})

        messages.success(request, msg)
        return redirect('student:historial')

    except Exception as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, f'Error al eliminar registro: {str(e)}')
        return redirect('student:historial')

@student_required
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
                
                if course_obj.credits > 0 and total_credits + course_obj.credits > 18:
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


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO MASIVO DE SEMESTRE COMPLETO
# ─────────────────────────────────────────────────────────────────────────────

@student_required
def bulk_save_academic_records_view(request):
    """
    Guarda o actualiza múltiples registros académicos en un solo request AJAX.
    Espera JSON con la estructura:
      {
        "semester": <int>,
        "records": [
          {"course_id": <int>, "status": "PASSED"|"FAILED"|"IN_PROGRESS", "grade": <float|null>},
          ...
        ]
      }
    Devuelve:
      {"success": true, "saved": <int>, "updated": <int>}
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    profile = _get_student_profile(request)
    if not profile:
        return JsonResponse({'success': False, 'error': 'Perfil de estudiante no encontrado'}, status=400)

    try:
        from apps.courses.models import Course
        from apps.academic.models import AcademicRecord
        from django.core.exceptions import ValidationError

        body = json.loads(request.body)
        semester = int(body.get('semester', profile.current_semester))
        records_data = body.get('records', [])

        if not records_data:
            return JsonResponse({'success': False, 'error': 'No se enviaron materias para guardar'}, status=400)

        # ── Validación de registro progresivo ─────────────────────────────────
        existing_records_all = list(
            AcademicRecord.objects.filter(student=profile).select_related('course')
        )
        registered_sems = sorted(set(r.semester_taken for r in existing_records_all))
        if registered_sems:
            max_continuous = 0
            for s in range(1, registered_sems[-1] + 2):
                if s in registered_sems:
                    max_continuous = s
                else:
                    break
            max_allowed = max_continuous + 1
        else:
            max_allowed = 1

        if semester > max_allowed:
            return JsonResponse({
                'success': False,
                'error': (
                    f'Registro progresivo requerido. Solo puedes registrar hasta el Semestre {max_allowed}. '
                    f'Primero registra el Semestre {max_allowed}.'
                )
            }, status=400)

        # ── Validación de materias obligatorias atrasadas ─────────────────────
        # Calcular materias con delay >= 3 que no están aprobadas ni en curso
        passed_ids = {r.course_id for r in existing_records_all if r.status == 'PASSED'}
        in_progress_ids = {r.course_id for r in existing_records_all if r.status == 'IN_PROGRESS'}
        all_program_courses = list(
            Course.objects.filter(program=profile.program, is_active=True)
        )
        mandatory_overdue = [
            c for c in all_program_courses
            if c.id not in passed_ids
            and c.id not in in_progress_ids
            and c.level < semester
            and (semester - c.level) >= 3
        ]
        # IDs de las materias obligatorias que vienen en el payload actual
        submitted_course_ids = {
            int(item['course_id']) for item in records_data
            if item.get('course_id') and item.get('status', 'SKIP').upper() != 'SKIP'
        }
        missing_mandatory = [
            c for c in mandatory_overdue
            if c.id not in submitted_course_ids
        ]
        if missing_mandatory:
            names = ', '.join(f'"{c.name.strip()}"' for c in missing_mandatory[:3])
            extra = f' y {len(missing_mandatory) - 3} más' if len(missing_mandatory) > 3 else ''
            return JsonResponse({
                'success': False,
                'error': (
                    f'Debes incluir en este semestre las materias obligatorias atrasadas (más de 3 semestres sin cursar): '
                    f'{names}{extra}. Son obligatorias y no pueden omitirse más.'
                )
            }, status=400)

        # ── Validación del límite de 18 créditos por semestre ─────────────────
        # Créditos de registros existentes en este semestre (que no serán sobreescritos)
        existing_in_sem = {
            r.course_id: r for r in existing_records_all if r.semester_taken == semester
        }
        # Créditos de los cursos que vienen en el payload
        new_course_ids_in_payload = set()
        total_payload_credits = 0
        for item in records_data:
            cid = item.get('course_id')
            st = (item.get('status') or 'SKIP').strip().upper()
            if not cid or st == 'SKIP':
                continue
            c = Course.objects.filter(id=cid, program=profile.program).first()
            if c:
                new_course_ids_in_payload.add(int(cid))
                total_payload_credits += c.credits

        # Créditos ya en el semestre pero NO en el payload (permanecen)
        carryover_credits = sum(
            r.course.credits for cid, r in existing_in_sem.items()
            if cid not in new_course_ids_in_payload
        )
        total_sem_credits = total_payload_credits + carryover_credits
        if total_sem_credits > 18:
            return JsonResponse({
                'success': False,
                'error': (
                    f'Límite de créditos superado. El Semestre {semester} tendría {total_sem_credits} créditos, '
                    f'superando el máximo permitido de 18 créditos.'
                )
            }, status=400)

        # ── Validación de materias ya aprobadas previamente y Prerrequisitos ──
        from apps.courses.models import Prerequisite
        passed_other_map = {
            r.course_id: r for r in existing_records_all
            if r.semester_taken != semester and r.status == 'PASSED'
        }
        passed_before_ids = {
            r.course_id for r in existing_records_all
            if r.semester_taken < semester and r.status == 'PASSED'
        }

        for item in records_data:
            cid = item.get('course_id')
            st = (item.get('status') or 'SKIP').strip().upper()
            if not cid or st == 'SKIP':
                continue
            cid = int(cid)

            # 1. Ya aprobada en otro semestre
            if cid in passed_other_map:
                prev_rec = passed_other_map[cid]
                c_obj = Course.objects.filter(id=cid).first()
                c_name = c_obj.name.strip() if c_obj else f'ID {cid}'
                return JsonResponse({
                    'success': False,
                    'error': (
                        f'La materia "{c_name}" ya fue aprobada en el Semestre {prev_rec.semester_taken} '
                        f'(calificación {prev_rec.grade}). No puedes volver a registrar una asignatura ya superada.'
                    )
                }, status=400)

            # 2. Prerrequisitos cumplidos en semestres estrictamente anteriores
            course_prereqs = Prerequisite.objects.filter(course_id=cid).select_related('required_course')
            unmet = []
            for p in course_prereqs:
                if p.required_course_id not in passed_before_ids:
                    unmet.append(f'"{p.required_course.name.strip()}"')

            if unmet:
                c_obj = Course.objects.filter(id=cid).first()
                c_name = c_obj.name.strip() if c_obj else f'ID {cid}'
                return JsonResponse({
                    'success': False,
                    'error': (
                        f'No puedes registrar "{c_name}" en el Semestre {semester}: '
                        f'requiere haber aprobado previamente los prerrequisitos: {", ".join(unmet)}.'
                    )
                }, status=400)

        saved_count = 0
        updated_count = 0
        errors = []

        for item in records_data:
            course_id = item.get('course_id')
            status = (item.get('status') or 'PASSED').strip().upper()
            grade_raw = item.get('grade')

            # Saltar filas donde no se ingresó información relevante
            if not course_id:
                continue
            if status == 'SKIP':
                continue

            # Validar curso
            course = Course.objects.filter(id=course_id, program=profile.program).first()
            if not course:
                errors.append(f'Materia con id {course_id} no encontrada o no pertenece al programa.')
                continue

            # Validar nota
            grade = None
            if grade_raw is not None and str(grade_raw).strip() != '':
                try:
                    grade = round(float(grade_raw), 2)
                    if grade < 0.0 or grade > 5.0:
                        errors.append(f'Nota inválida para "{course.name}": debe estar entre 0.0 y 5.0.')
                        continue
                except (ValueError, TypeError):
                    errors.append(f'Nota inválida para "{course.name}".')
                    continue

            # Ajustar estado automáticamente según nota (>= 3.0 aprueba, < 3.0 reprueba)
            if status == 'IN_PROGRESS':
                grade = None
            elif grade is not None:
                status = 'PASSED' if grade >= 3.0 else 'FAILED'
            else:
                if status == 'PASSED':
                    grade = 3.5
                elif status == 'FAILED':
                    grade = 2.0

            # Crear o actualizar el registro EN ESTE SEMESTRE ESPECÍFICO
            existing = AcademicRecord.objects.filter(
                student=profile, course=course, semester_taken=semester
            ).first()
            if existing:
                existing.status = status
                existing.grade = grade
                existing.full_clean()
                existing.save()
                updated_count += 1
            else:
                record = AcademicRecord(
                    student=profile,
                    course=course,
                    semester_taken=semester,
                    status=status,
                    grade=grade,
                )
                record.full_clean()
                record.save()
                saved_count += 1

        return JsonResponse({
            'success': True,
            'saved': saved_count,
            'updated': updated_count,
            'errors': errors,
            'message': f'Semestre {semester} guardado: {saved_count} nuevas, {updated_count} actualizadas.'
                       + (f' ({len(errors)} con errores)' if errors else ''),
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON inválido en el cuerpo de la solicitud'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# LIMPIEZA DE HISTORIAL ACADÉMICO
# ─────────────────────────────────────────────────────────────────────────────

@student_required
def clear_all_history_view(request):
    """
    Elimina TODO el historial académico del estudiante autenticado.
    Solo acepta POST (con CSRF). Devuelve JSON si es AJAX.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    profile = _get_student_profile(request)
    if not profile:
        return JsonResponse({'success': False, 'error': 'Perfil no encontrado'}, status=400)

    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.content_type
    )

    try:
        from apps.academic.models import AcademicRecord
        deleted_count, _ = AcademicRecord.objects.filter(student=profile).delete()
        msg = (
            f'Historial académico limpiado: {deleted_count} registro(s) eliminado(s).'
            if deleted_count else
            'El historial ya estaba vacío.'
        )
        if is_ajax:
            return JsonResponse({'success': True, 'message': msg, 'deleted': deleted_count})
        messages.success(request, msg)
    except Exception as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, f'Error al limpiar historial: {e}')

    return redirect('student:historial')


@student_required
def clear_semester_history_view(request):
    """
    Elimina todos los registros académicos de un semestre específico.
    Espera POST con body JSON: {"semester": <int>}
    Devuelve JSON si es AJAX.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    profile = _get_student_profile(request)
    if not profile:
        return JsonResponse({'success': False, 'error': 'Perfil no encontrado'}, status=400)

    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.content_type
    )

    try:
        from apps.academic.models import AcademicRecord

        if 'application/json' in request.content_type:
            body = json.loads(request.body)
            semester = int(body.get('semester', 0))
        else:
            semester = int(request.POST.get('semester', 0))

        if not semester or semester < 1:
            err = 'Número de semestre inválido.'
            if is_ajax:
                return JsonResponse({'success': False, 'error': err}, status=400)
            messages.error(request, err)
            return redirect('student:historial')

        deleted_count, _ = AcademicRecord.objects.filter(
            student=profile, semester_taken=semester
        ).delete()

        msg = (
            f'Semestre {semester} limpiado: {deleted_count} registro(s) eliminado(s).'
            if deleted_count else
            f'El Semestre {semester} no tenía registros.'
        )
        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': msg,
                'deleted': deleted_count,
                'semester': semester,
            })
        messages.success(request, msg)

    except (ValueError, json.JSONDecodeError):
        err = 'Datos inválidos en la solicitud.'
        if is_ajax:
            return JsonResponse({'success': False, 'error': err}, status=400)
        messages.error(request, err)
    except Exception as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, f'Error al limpiar semestre: {e}')

    return redirect('student:historial')
