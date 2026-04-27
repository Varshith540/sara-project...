from django.contrib import admin
from .models import Resume, AnalysisResult, ExamQuestion, ExamAttempt


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display  = ('name', 'email', 'phone', 'uploaded_at')
    search_fields = ('name', 'email')
    readonly_fields = ('raw_text',)


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display  = ('resume', 'ats_score', 'skill_match_score', 'cosine_score', 'created_at')
    list_filter   = ('created_at',)
    readonly_fields = ('matched_skills', 'missing_skills', 'suggestions')


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display  = ('skill', 'question')
    list_filter   = ('skill',)
    search_fields = ('question', 'skill')


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ('result', 'score', 'total', 'attempted_at')
