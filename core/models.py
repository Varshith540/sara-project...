"""
ResumeXpert – Database Models
"""

from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Resume upload record
# ---------------------------------------------------------------------------
class Resume(models.Model):
    name        = models.CharField(max_length=200, blank=True, default='Unknown')
    email       = models.EmailField(blank=True, default='')
    phone       = models.CharField(max_length=30, blank=True, default='')
    file        = models.FileField(upload_to='resumes/')
    raw_text    = models.TextField(blank=True, default='')
    uploaded_at = models.DateTimeField(default=timezone.now)

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
    created_at          = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Analysis for {self.resume.name} – Score: {self.ats_score}%"

    # Helper used in template
    def score_color(self):
        if self.ats_score >= 75:
            return 'success'
        if self.ats_score >= 50:
            return 'warning'
        return 'danger'

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
    attempted_at = models.DateTimeField(default=timezone.now)

    def percentage(self):
        if self.total == 0:
            return 0
        return round((self.score / self.total) * 100, 1)

    def __str__(self):
        return f"Attempt by {self.result.resume.name} – {self.score}/{self.total}"
