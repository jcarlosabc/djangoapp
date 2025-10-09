from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages # <-- Añadido
from .models import Survey, Section, Question, ResponseSet, Answer, DOCUMENT_TYPES, Ubicacion, Municipio, Interviewer
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


from django.db.models import Model

# Helper to convert cleaned_data to a JSON-serializable dict
def cleaned_data_to_json(cleaned_data):
    json_data = {}
    for key, value in cleaned_data.items():
        if isinstance(value, Model):
            json_data[key] = value.pk
        elif isinstance(value, list):
            json_data[key] = [v.pk if isinstance(v, Model) else v for v in value]
        else:
            json_data[key] = value
    return json_data

@login_required
def survey_fill(request, survey_code):
    survey = get_object_or_404(Survey, code=survey_code, is_active=True)
    sections = survey.sections.all()
    url = reverse('surveys:fill', kwargs={'survey_code': survey_code})

    # Initialize session data
    if 'survey_answers' not in request.session:
        request.session['survey_answers'] = {}
    if 'respondent_data' not in request.session:
        request.session['respondent_data'] = {}

    is_respondent_step = 'section' not in request.GET

    # If this is a GET request for the very first step, clear any old session data.
    if request.method == 'GET' and is_respondent_step:
        if 'survey_answers' in request.session:
            del request.session['survey_answers']
        if 'respondent_data' in request.session:
            del request.session['respondent_data']
        request.session.modified = True

    if request.method == 'POST':
        if request.POST.get('step_name') == 'respondent':
            if request.POST.get('data_protection_consent_value') != 'yes':
                respondent_form = ResponseSetForm(request.POST, document_types=DOCUMENT_TYPES)
                context = {
                    'survey': survey,
                    'respondent_form': respondent_form,
                    'is_respondent_step': True,
                    'consent_error': 'Debes aceptar la cláusula de protección de datos para continuar.'
                }
                return render(request, 'surveys/survey_fill_steps.html', context)

            respondent_form = ResponseSetForm(request.POST, document_types=DOCUMENT_TYPES)
            if respondent_form.is_valid():
                request.session['respondent_data'] = cleaned_data_to_json(respondent_form.cleaned_data)
                request.session.modified = True
                return redirect(f"{url}?section=0")
            else:
                # Re-render respondent step with errors
                context = {
                    'survey': survey,
                    'respondent_form': respondent_form,
                    'is_respondent_step': True,
                }
                return render(request, 'surveys/survey_fill_steps.html', context)
        else:
            current_section_idx = int(request.GET.get('section', 0))
            current_section = sections[current_section_idx]
            AnswersForm = build_answers_form_for_section(current_section)
            answers_form = AnswersForm(request.POST)

            if answers_form.is_valid():
                request.session['survey_answers'][str(current_section.pk)] = cleaned_data_to_json(answers_form.cleaned_data)
                request.session.modified = True

                if current_section_idx == len(sections) - 1:
                    # --- SAVE TO DB LOGIC (same as before) ---
                    with transaction.atomic():
                        respondent_data = request.session.get('respondent_data', {})
                        interviewer_id = respondent_data.get('interviewer')
                        interviewer_instance = Interviewer.objects.get(pk=interviewer_id) if interviewer_id else None

                        response_set, _ = ResponseSet.objects.get_or_create(
                            survey=survey,
                            identificacion=respondent_data.get('identificacion'),
                            document_type=respondent_data.get('document_type'),
                            defaults={
                                'full_name': respondent_data.get('full_name'),
                                'email': respondent_data.get('email'),
                                'phone': respondent_data.get('phone'),
                                'user': request.user,
                                'interviewer': interviewer_instance,
                            }
                        )

                        for section_pk, section_answers in request.session.get('survey_answers', {}).items():
                            section_obj = Section.objects.get(pk=section_pk)
                            for question in section_obj.questions.all():
                                field_name = f"question_{question.pk}"
                                if question.qtype == 'ubicacion':
                                    field_name = f"question_{question.pk}_ubicacion"
                                
                                answer_value = section_answers.get(field_name)
                                
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
                                elif question.qtype == 'ubicacion':
                                    if answer_value:
                                        answer.selected_ubicaciones.set([answer_value])
                                    else:
                                        answer.selected_ubicaciones.clear()
                    
                    del request.session['survey_answers']
                    del request.session['respondent_data']
                    messages.success(request, '¡Encuesta guardada exitosamente!')
                    return render(request, 'surveys/survey_complete.html', {'survey': survey})
                else:
                    next_section_idx = current_section_idx + 1
                    return redirect(f"{url}?section={next_section_idx}")
            else:
                # Re-render section step with errors
                context = {
                    'survey': survey,
                    'section': current_section,
                    'answers_form': answers_form,
                    'current_section_idx': current_section_idx,
                    'total_sections': len(sections),
                    'is_respondent_step': False,
                }
                return render(request, 'surveys/survey_fill_steps.html', context)

    # GET request logic
    if is_respondent_step:
        respondent_form = ResponseSetForm(initial=request.session.get('respondent_data', {}), document_types=DOCUMENT_TYPES)
        context = {
            'survey': survey,
            'respondent_form': respondent_form,
            'is_respondent_step': True,
        }
    else:
        current_section_idx = int(request.GET.get('section', 0))
        if not sections.exists() or current_section_idx >= len(sections):
            return redirect('surveys:list')
        
        current_section = sections[current_section_idx]
        AnswersForm = build_answers_form_for_section(current_section)
        answers_form = AnswersForm(initial=request.session.get('survey_answers', {}).get(str(current_section.pk), {}))
        context = {
            'survey': survey,
            'section': current_section,
            'answers_form': answers_form,
            'current_section_idx': current_section_idx,
            'total_sections': len(sections),
            'is_respondent_step': False,
        }
    
    return render(request, 'surveys/survey_fill_steps.html', context)

def get_ubicaciones(request):
    municipio_id = request.GET.get('municipio_id')
    ubicaciones = Ubicacion.objects.filter(municipio_id=municipio_id).order_by('nombre')
    return JsonResponse(list(ubicaciones.values('id', 'nombre')), safe=False)

def get_ubicacion_details(request):
    ubicacion_id = request.GET.get('ubicacion_id')
    ubicacion = get_object_or_404(Ubicacion, pk=ubicacion_id)
    return JsonResponse({'loc': ubicacion.loc, 'zona': ubicacion.zona})