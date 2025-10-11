from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

app_name = "surveys"

urlpatterns = [
    path("", views.survey_list, name="list"),
    path("public/", views.survey_list_public, name="public_list"),
    path("s/<slug:survey_code>/", views.survey_fill, name="fill"), # Changed 'code' to 'survey_code'
    path("s/<slug:survey_code>/check-respondent/", views.check_duplicate_respondent, name="check_respondent"), # Changed 'code' to 'survey_code'
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(template_name="surveys/auth_login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # AJAX
    path('ajax/get_ubicaciones/', views.get_ubicaciones, name='get_ubicaciones'),
    path('ajax/get_ubicacion_details/', views.get_ubicacion_details, name='get_ubicacion_details'),
    path('ajax/get_question_dependency_data/', views.get_question_dependency_data, name='get_question_dependency_data'),
]