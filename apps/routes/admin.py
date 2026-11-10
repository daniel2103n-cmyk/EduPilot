from django.contrib import admin
from .models import SavedRoute, SavedRouteSemester, SavedRouteCourse, SavedSchedule, SavedScheduleItem


class SavedRouteCourseInline(admin.TabularInline):
    model = SavedRouteCourse
    extra = 0


class SavedRouteSemesterInline(admin.StackedInline):
    model = SavedRouteSemester
    extra = 0


@admin.register(SavedRoute)
class SavedRouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'student', 'program', 'strategy_key', 'estimated_semesters', 'is_favorite', 'created_at')
    list_filter = ('strategy_key', 'is_favorite', 'program')
    search_fields = ('name', 'student__user__username')
    inlines = [SavedRouteSemesterInline]


class SavedScheduleItemInline(admin.TabularInline):
    model = SavedScheduleItem
    extra = 0


@admin.register(SavedSchedule)
class SavedScheduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'student', 'academic_period', 'is_valid', 'is_pending_review', 'created_at')
    list_filter = ('academic_period', 'is_valid', 'is_pending_review')
    search_fields = ('name', 'student__user__username')
    inlines = [SavedScheduleItemInline]
