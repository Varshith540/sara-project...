"""
ResumeXpert – Database Models
"""

from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Resume upload record
# ---------------------------------------------------------------------------
class Resume(models.Model):
    name            = models.CharField(max_length=200, blank=True, default='Unknown')
    email           = models.EmailField(blank=True, default='')
    phone           = models.CharField(max_length=30, blank=True, default='')
    target_industry = models.CharField(max_length=100, blank=True, default='')
    file            = models.FileField(upload_to='resumes/')
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    raw_text        = models.TextField(blank=True, default='')
    uploaded_at     = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.name} ({self.uploaded_at.strftime('%d %b %Y')})"

    def filename(self):
        return self.file.name.split('/')[-1]


# ---------------------------------------------------------------------------
# Analysis result linked to a resume
# ---------------------------------------------------------------------------
class AnalysisResult(models.Model):
    resume              = models.OneToOneField(Resume, on_delete=models.CASCADE,
                                               related_name='result')
    job_description     = models.TextField()
    ats_score           = models.FloatField(default=0.0)
    skill_match_score   = models.FloatField(default=0.0)
    cosine_score        = models.FloatField(default=0.0)
    matched_skills      = models.JSONField(default=list)
    missing_skills      = models.JSONField(default=list)
    resume_skills       = models.JSONField(default=list)
    suggestions         = models.JSONField(default=list)
    # --- Gemini AI fields ---------------------------------------------------
    ai_summary          = models.TextField(blank=True, default='')
    ai_suggestions      = models.JSONField(default=list)
    interview_questions = models.JSONField(default=list)
    job_fit_score       = models.IntegerField(default=0)
    # --- AI Resume Rewriter fields ------------------------------------------
    rewritten_resume    = models.TextField(blank=True, default='')
    improvement_notes   = models.JSONField(default=list)
    # --- Company Analysis fields --------------------------------------------
    company_name        = models.CharField(max_length=200, blank=True, default='')
    company_analysis    = models.JSONField(default=dict)
    
    active_ai_model     = models.CharField(max_length=100, default='Gemini')
    created_at          = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Analysis for {self.resume.name} – Score: {self.ats_score}%"

    # Helper used in template
    @property
    def score_color(self):
        if self.ats_score >= 75:
            return 'success'
        if self.ats_score >= 50:
            return 'warning'
        return 'danger'

    @property
    def score_label(self):
        if self.ats_score >= 75:
            return 'Excellent'
        if self.ats_score >= 50:
            return 'Good'
        if self.ats_score >= 30:
            return 'Fair'
        return 'Needs Improvement'


# ---------------------------------------------------------------------------
# Exam question bank
# ---------------------------------------------------------------------------
class ExamQuestion(models.Model):
    skill          = models.CharField(max_length=100)
    question       = models.TextField()
    option_a       = models.CharField(max_length=300)
    option_b       = models.CharField(max_length=300)
    option_c       = models.CharField(max_length=300)
    option_d       = models.CharField(max_length=300)
    correct_option = models.CharField(
        max_length=1,
        choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')]
    )
    explanation    = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['skill']

    def __str__(self):
        return f"[{self.skill}] {self.question[:60]}"

    def options_list(self):
        return [self.option_a, self.option_b, self.option_c, self.option_d]


# ---------------------------------------------------------------------------
# Exam attempt / session
# ---------------------------------------------------------------------------
class ExamAttempt(models.Model):
    result       = models.ForeignKey(AnalysisResult, on_delete=models.CASCADE,
                                     related_name='attempts')
    score        = models.IntegerField(default=0)
    total        = models.IntegerField(default=0)
    answers      = models.JSONField(default=dict)   # {question_id: chosen_option}
    sector       = models.CharField(max_length=100, blank=True, default='')
    difficulty   = models.CharField(max_length=20, default='Intermediate')
    time_limit   = models.IntegerField(default=30)  # in minutes
    attempted_at = models.DateTimeField(default=timezone.now)

    def percentage(self):
        if self.total == 0:
            return 0
        return round((self.score / self.total) * 100, 1)

    def __str__(self):
        return f"Attempt by {self.result.resume.name} – {self.score}/{self.total}"


# ---------------------------------------------------------------------------
# AI Self-Improvement Loop
# ---------------------------------------------------------------------------
class AIFeedback(models.Model):
    """
    Stores user feedback (Like/Apply) on specific AI-generated suggestions.
    This database helps the agent 'learn' which keywords/phrases get the best responses.
    """
    suggestion_text = models.TextField()
    action_taken    = models.CharField(max_length=50, choices=[('like', 'Like'), ('apply', 'Apply')])
    created_at      = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"[{self.action_taken.upper()}] {self.suggestion_text[:50]}"


class IndustryTrend(models.Model):
    """
    Stores the latest hiring trends fetched by the background freshness check cron job.
    """
    sector       = models.CharField(max_length=100)
    keywords     = models.JSONField(default=list)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Trends for {self.sector} (Updated: {self.updated_at.strftime('%Y-%m-%d')})"
