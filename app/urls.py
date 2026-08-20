from django.urls import path

from . import views

urlpatterns = [
    path('questions/', views.question_list, name='question-list'),
    path('templates/', views.template_list, name='template-list'),
    path('generations/', views.generation_create, name='generation-create'),
    path(
        'generations/<uuid:pk>/',
        views.GenerationDetail.as_view(),
        name='generation-detail',
    ),
]
