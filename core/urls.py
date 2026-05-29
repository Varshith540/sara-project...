"""
ResumeXpert – Core App URL Patterns
"""

from django.urls import path
from . import views
from core.views_telemetry import FrontendTelemetryView

urlpatterns = [
    path('',                          views.upload_resume,  name='upload'),
    path('dashboard/<int:pk>/',       views.dashboard,      name='dashboard'),
    path('history/',                  views.history,        name='history'),
    path('exam/<int:pk>/',            views.exam_view,      name='exam'),
    path('exam/<int:pk>/submit/',     views.exam_submit,    name='exam_submit'),
    path('delete/<int:pk>/',          views.delete_result,  name='delete_result'),
    path('resume/<int:pk>/generate/', views.generate_resume,name='generate_resume'),
    path('company/<int:pk>/',         views.company_analysis,name='company_analysis'),
    path('api/trending-skills/',      views.get_trending_skills,name='api_trending_skills'),
    path('api/feedback/',             views.submit_feedback,name='api_submit_feedback'),
    path('api/chat/',                 views.sri_ai_chat,    name='sri_ai_chat'),
    path('api/chat/diagnostics/',     views.chat_diagnostics, name='chat_diagnostics'),
    path('resume/<int:pk>/upload-photo/', views.upload_resume_photo, name='upload_resume_photo'),
    path('builder/',                  views.resume_builder, name='resume_builder'),
    path('api/compare/',              views.compare_resumes,name='api_compare_resumes'),
    path('ping/',                     views.ping_alive,          name='ping_alive'),
    path('health/',                   views.deep_health_check,   name='deep_health_check'),
    
    # Sri AI CI/CD One-Click Webhook
    path('api/cicd/approve-deployment/<str:token>/', views.sri_approve_deployment, name='sri_approve_deployment'),
    path('api/cicd/reject-deployment/<str:token>/', views.sri_reject_deployment, name='sri_reject_deployment'),
    
    # Mock Interview
    path('interview/<int:pk>/', views.mock_interview, name='mock_interview'),
    path('api/interview/evaluate/', views.api_evaluate_answer, name='api_evaluate_answer'),

    # ── Sri AI Omni-Heal Telemetry ─────────────────────────────
    path('api/sri-heal/frontend/', FrontendTelemetryView.as_view(), name='sri_frontend_telemetry'),
]
