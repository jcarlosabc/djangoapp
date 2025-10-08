from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages # <-- Añadido
from .models import Survey, Section, Question, ResponseSet, Answer, DOCUMENT_TYPES
from .forms import ResponseSetForm, build_answers_form_for_section
from .forms_signup import SignUpForm

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('surveys:list')
    else:
        form = SignUpForm()
    return render(request, 'surveys/auth_signup.html', {'form': form})

def survey_list_public(request): # New public survey list view
    surveys = Survey.objects.filter(is_active=True)
    return render(request, 'surveys/survey_list.html', {'surveys': surveys})

@login_required
def survey_list(request):
    surveys = Survey.objects.filter(is_active=True)
    return render(request, 'surveys/survey_list.html', {'surveys': surveys})

def check_duplicate_respondent(request, survey_code):
    if request.method == 'POST':
        identificacion = request.POST.get('identificacion', '').strip()
        document_type = request.POST.get('document_type', '').strip()
        
        # Validar que ambos campos estén presentes
        if not identificacion or not document_type:
            return JsonResponse({
                'valid': False,
                'message': 'Debes proporcionar el documento y tipo de documento.'
            })
        
        # Get the survey instance
        survey = get_object_or_404(Survey, code=survey_code)

        # Check if a ResponseSet already exists for this survey, identification, and document type
        is_duplicate = ResponseSet.objects.filter(
            survey=survey,
            identificacion=identificacion,
            document_type=document_type
        ).exists()
        
        # Retornar 'valid' (no 'is_duplicate') - válido si NO es duplicado
        return JsonResponse({
            'valid': not is_duplicate,  # ← Cambio importante: invertir la lógica
            'message': 'Esta persona ya respondió esta encuesta.' if is_duplicate else ''
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)


@login_required
def survey_fill(request, survey_code):
    print("DEBUG: survey_fill function called.")
    survey = get_object_or_404(Survey, code=survey_code, is_active=True)
    sections = survey.sections.all()
    current_section_idx = int(request.GET.get('section', 0))

    if not sections.exists() or current_section_idx >= len(sections):
        print("DEBUG: Redirecting to survey list (sections not exist or current_section_idx out of bounds).")
        return redirect('surveys:list')

    current_section = sections[current_section_idx]

    sections_forms = []
    for i, section_obj in enumerate(sections):
        AnswersForm = build_answers_form_for_section(section_obj)
        if i == current_section_idx and request.method == 'POST':
            form_instance = AnswersForm(request.POST)
        else:
            form_instance = AnswersForm()
        sections_forms.append((section_obj, form_instance))

    if request.method == 'POST':
        respondent_form = ResponseSetForm(request.POST, document_types=DOCUMENT_TYPES)
        answers_form_current_section = sections_forms[current_section_idx][1]

        print(f"DEBUG: current_section_idx: {current_section_idx}")
        print(f"DEBUG: respondent_form is_valid: {respondent_form.is_valid()}")
        if not respondent_form.is_valid():
            print(f"DEBUG: respondent_form errors: {respondent_form.errors}")
        print(f"DEBUG: answers_form_current_section is_valid: {answers_form_current_section.is_valid()}")
        if not answers_form_current_section.is_valid():
            print(f"DEBUG: answers_form_current_section errors: {answers_form_current_section.errors}")

        if respondent_form.is_valid() and answers_form_current_section.is_valid():
            with transaction.atomic():
                identificacion = respondent_form.cleaned_data['identificacion']
                document_type = respondent_form.cleaned_data['document_type']
                response_set, created = ResponseSet.objects.get_or_create(
                    survey=survey,
                    identificacion=identificacion,
                    document_type=document_type,
                    defaults={
                        'full_name': respondent_form.cleaned_data['full_name'],
                        'email': respondent_form.cleaned_data['email'],
                        'phone': respondent_form.cleaned_data['phone'],
                        'user': request.user,
                        'interviewer': respondent_form.cleaned_data.get('interviewer'),
                    }
                )
                if not created:
                    response_set.full_name = respondent_form.cleaned_data['full_name']
                    response_set.email = respondent_form.cleaned_data['email']
                    response_set.phone = respondent_form.cleaned_data['phone']
                    response_set.user = request.user
                    response_set.interviewer = respondent_form.cleaned_data.get('interviewer')
                    response_set.save()

                for question in current_section.questions.all():
                    field_name = f"question_{question.pk}"
                    answer_value = answers_form_current_section.cleaned_data.get(field_name)
                    print(f"DEBUG: Question {question.pk} ({question.text}), answer_value: {answer_value}")

                    answer, _ = Answer.objects.update_or_create(
                        response=response_set,
                        question=question,
                        defaults={
                            'text_answer': answer_value if question.qtype == 'text' else '',
                            'integer_answer': answer_value if question.qtype == 'int' else None,
                            'decimal_answer': answer_value if question.qtype == 'dec' else None,
                            'bool_answer': answer_value if question.qtype == 'bool' else None,
                            'date_answer': answer_value if question.qtype == 'date' else None,
                        }
                    )
                    if question.qtype in ['single', 'multi', 'likert']:
                        if answer_value:
                            if not isinstance(answer_value, list):
                                answer_value = [answer_value]
                            answer.options.set(answer_value)
                        else:
                            answer.options.clear()
                    elif question.qtype == 'barrio':
                        if answer_value:
                            if not isinstance(answer_value, list):
                                answer_value = [answer_value]
                            answer.selected_barrios.set(answer_value)
                        else:
                            answer.selected_barrios.clear()

            next_section_idx = current_section_idx + 1
            print(f"DEBUG: next_section_idx: {next_section_idx}, len(sections): {len(sections)}")
            if next_section_idx < len(sections):
                url = reverse('surveys:fill', kwargs={'survey_code': survey_code})
                print(f"DEBUG: Redirecting to next section: {url}?section={next_section_idx}")
                return redirect(f"{url}?section={next_section_idx}")
            else:
                messages.success(request, '¡Encuesta guardada exitosamente!')
                print("DEBUG: Survey completed. Rendering survey_complete.html.")
                return render(request, 'surveys/survey_complete.html', {'survey': survey})
        else:
            respondent_form = ResponseSetForm(request.POST, document_types=DOCUMENT_TYPES)
            print("DEBUG: Forms not valid, re-rendering current section.")
    else: # GET request
        print("DEBUG: GET request. Initializing forms.")
        respondent_form = ResponseSetForm(document_types=DOCUMENT_TYPES)

    context = {
        'survey': survey,
        'section': current_section,
        'respondent_form': respondent_form,
        'sections_forms': sections_forms,
        'current_section_idx': current_section_idx,
        'total_sections': len(sections),
    }
    print("DEBUG: Rendering survey_fill_steps.html.")
    return render(request, 'surveys/survey_fill_steps.html', context)