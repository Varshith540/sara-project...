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
]
