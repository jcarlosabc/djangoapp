
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .forms import RespondentForm, build_answers_form_for_section
from .models import Answer, QuestionType, ResponseSet, Survey

def survey_list_public(request):
    surveys = Survey.objects.filter(is_active=True).order_by("-created_at")
    return render(request, "surveys/survey_list.html", {"surveys": surveys, "public": True})

@login_required
def survey_list(request):
    surveys = Survey.objects.filter(is_active=True).order_by("-created_at")
    return render(request, "surveys/survey_list.html", {"surveys": surveys})

def survey_fill(request, code):
    survey = get_object_or_404(Survey, code=code, is_active=True)
    show_interviewer = request.user.is_authenticated

    section_forms = []
    for section in survey.sections.all():
        AnswersForm = build_answers_form_for_section(section)
        if request.method == "POST":
            form = AnswersForm(request.POST, prefix=f"sec{section.id}")
        else:
            form = AnswersForm(prefix=f"sec{section.id}")
        section_forms.append((section, form))

    if request.method == "POST":
        resp_form = RespondentForm(request.POST, survey=survey, show_interviewer=show_interviewer)
    else:
        resp_form = RespondentForm(survey=survey, show_interviewer=show_interviewer)

    if request.method == "POST":
        all_valid = resp_form.is_valid() and all(f.is_valid() for _, f in section_forms)
        if all_valid:
            try:
                with transaction.atomic():
                    rs = resp_form.save(commit=False)
                    rs.survey = survey
                    if request.user.is_authenticated:
                        rs.user = request.user
                    else:
                        rs.interviewer_id = None
                    rs.save()

                    for section, form in section_forms:
                        for q in section.questions.all():
                            name = f"q_{q.id}"
                            val = form.cleaned_data.get(name)
                            ans = Answer.objects.create(response=rs, question=q)

                            if q.qtype in (QuestionType.SINGLE, QuestionType.LIKERT):
                                if val: ans.options.set([int(val)])
                            elif q.qtype == QuestionType.MULTI:
                                ids = [int(v) for v in (val or [])]
                                if ids: ans.options.set(ids)
                            elif q.qtype == QuestionType.TEXT:
                                ans.text_answer = val or ""
                            elif q.qtype == QuestionType.INTEGER:
                                ans.integer_answer = val
                            elif q.qtype == QuestionType.DECIMAL:
                                ans.decimal_answer = val
                            elif q.qtype == QuestionType.BOOL:
                                ans.bool_answer = val
                            elif q.qtype == QuestionType.DATE:
                                ans.date_answer = val
                            ans.full_clean()
                            ans.save()

            except IntegrityError:
                messages.error(request, "Registro duplicado: esta persona ya respondiÃ³ esta encuesta.")
            else:
                messages.success(request, "Â¡Gracias! Respuesta registrada correctamente.")
                return redirect("surveys:list")

    return render(request, "surveys/survey_fill_steps.html", {
        "survey": survey,
        "resp_form": resp_form,
        "sections_forms": section_forms,
        "public": not request.user.is_authenticated,
    })

@require_POST
def check_duplicate_respondent(request, code):
    survey = get_object_or_404(Survey, code=code, is_active=True)
    ident = (request.POST.get("identificacion") or "").strip()
    doc_type = (request.POST.get("document_type") or "").strip()
    if not ident or not doc_type:
        return JsonResponse(
            {
                "valid": False,
                "message": "Debes ingresar la identificacion y el tipo de documento.",
            },
            status=400,
        )
    exists = ResponseSet.objects.filter(
        survey=survey,
        identificacion=ident,
        document_type=doc_type,
    ).exists()
    if exists:
        return JsonResponse(
            {
                "valid": False,
                "message": "Esta persona ya respondio esta encuesta (no se permite duplicidad).",
            }
        )
    return JsonResponse({"valid": True})

def signup(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("surveys:list")
    else:
        form = UserCreationForm()
    return render(request, "surveys/auth_signup.html", {"form": form})

