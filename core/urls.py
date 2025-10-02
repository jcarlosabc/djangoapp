from django.urls import path
from . import views


app_name = "surveys"


urlpatterns = [
path("<int:survey_id>/", views.survey_form, name="form"),
path("<int:survey_id>/ident/", views.ident_partial, name="ident_partial"),
path("<int:survey_id>/check/", views.check_ident, name="check_ident"),
path("<int:survey_id>/submit/", views.submit_response, name="submit"),
]