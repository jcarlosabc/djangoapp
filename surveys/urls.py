
from django.urls import path
from . import views

app_name = "surveys"

urlpatterns = [
    path("", views.survey_list, name="list"),
    path("s/<slug:code>/", views.survey_fill, name="fill"),
    path("s/<slug:code>/check-respondent/", views.check_duplicate_respondent, name="check_respondent"),
]
