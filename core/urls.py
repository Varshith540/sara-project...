"""
ResumeXpert – Core App URL Patterns
"""

from django.urls import path
from . import views

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
    path('resume/<int:pk>/upload-photo/', views.upload_resume_photo, name='upload_resume_photo'),
    path('builder/',                  views.resume_builder, name='resume_builder'),
    path('api/compare/',              views.compare_resumes,name='api_compare_resumes'),
    path('ping/',                     views.ping_alive,     name='ping_alive'),
]
