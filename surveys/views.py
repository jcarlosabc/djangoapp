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
    
    # Initialize session data
    if 'survey_answers' not in request.session:
        request.session['survey_answers'] = {}
    if 'respondent_data' not in request.session:
        request.session['respondent_data'] = {}

    current_section_idx = int(request.GET.get('section', 0))
    
    if not sections.exists() or current_section_idx >= len(sections):
        return redirect('surveys:list')

    current_section = sections[current_section_idx]
    AnswersForm = build_answers_form_for_section(current_section)

    if request.method == 'POST':
        # Respondent form is only on the first section
        if current_section_idx == 0:
            respondent_form = ResponseSetForm(request.POST, document_types=DOCUMENT_TYPES)
            if respondent_form.is_valid():
                request.session['respondent_data'] = cleaned_data_to_json(respondent_form.cleaned_data)
                request.session.modified = True
            else:
                # Show errors and stay on the same page
                answers_form = AnswersForm()
                return render(request, 'surveys/survey_fill_steps.html', {
                    'survey': survey,
                    'section': current_section,
                    'respondent_form': respondent_form,
                    'answers_form': answers_form,
                    'current_section_idx': current_section_idx,
                    'total_sections': len(sections),
                })
        
        answers_form = AnswersForm(request.POST)
        if answers_form.is_valid():
            # Store current section answers
            request.session['survey_answers'][str(current_section.pk)] = cleaned_data_to_json(answers_form.cleaned_data)
            request.session.modified = True

            # If last section, save everything
            if current_section_idx == len(sections) - 1:
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
                
                # Clean up session
                del request.session['survey_answers']
                del request.session['respondent_data']
                
                messages.success(request, '¡Encuesta guardada exitosamente!')
                return render(request, 'surveys/survey_complete.html', {'survey': survey})

            # Not the last section, redirect to the next one
            else:
                next_section_idx = current_section_idx + 1
                url = reverse('surveys:fill', kwargs={'survey_code': survey_code})
                return redirect(f"{url}?section={next_section_idx}")
        else:
            # Show errors and stay on the same page
            respondent_form = ResponseSetForm(request.session.get('respondent_data', {}), document_types=DOCUMENT_TYPES)
            return render(request, 'surveys/survey_fill_steps.html', {
                'survey': survey,
                'section': current_section,
                'respondent_form': respondent_form,
                'answers_form': answers_form,
                'current_section_idx': current_section_idx,
                'total_sections': len(sections),
            })

    else: # GET request
        # If it's the first section, show the respondent form
        if current_section_idx == 0:
            respondent_form = ResponseSetForm(initial=request.session.get('respondent_data', {}), document_types=DOCUMENT_TYPES)
        else:
            respondent_form = None
        
        # Populate answers form with session data if available
        answers_form = AnswersForm(initial=request.session.get('survey_answers', {}).get(str(current_section.pk), {}))

    context = {
        'survey': survey,
        'section': current_section,
        'respondent_form': respondent_form,
        'answers_form': answers_form,
        'current_section_idx': current_section_idx,
        'total_sections': len(sections),
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