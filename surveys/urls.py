
from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

app_name = "surveys"

urlpatterns = [
    path("", views.survey_list, name="list"),
    path("public/", views.survey_list_public, name="public_list"),
    path("s/<slug:code>/", views.survey_fill, name="fill"),
    path("s/<slug:code>/check-respondent/", views.check_duplicate_respondent, name="check_respondent"),
    path("signup/", views.signup, name="signup"),
    path("login/", auth_views.LoginView.as_view(template_name="surveys/auth_login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
