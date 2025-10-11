from django.conf import settings # Added
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages # <-- Añadido
from .models import Survey, Section, Question, ResponseSet, Answer, DOCUMENT_TYPES, Ubicacion, Municipio, Interviewer, QuestionType, Option, SingleChoiceDisplayType, SingleChoiceDisplayType
from .forms import ResponseSetForm, build_answers_form_for_section, SurveyUploadForm
from .forms_signup import SignUpForm
import pandas as pd
from django.utils.text import slugify

def _process_survey_excel(excel_file, status_callback):
    try:
        df = pd.read_excel(excel_file)
    except Exception as e:
        status_callback('error', f"Error al leer el archivo Excel: {e}")
        return

    required_columns = ['survey_title', 'text', 'type', 'order']
    if not all(col in df.columns for col in required_columns):
        status_callback('error', f"El archivo Excel debe contener las siguientes columnas: {', '.join(required_columns)}")
        return

    surveys_cache = {}
    sections_cache = {}
    questions_cache = {}

    status_callback('info', "Iniciando el proceso de carga de la encuesta...")

    for index, row in df.iterrows():
        try:
            survey_title = row['survey_title'].strip()
            if survey_title not in surveys_cache:
                survey_code = slugify(survey_title)
                survey, created = Survey.objects.get_or_create(
                    code=survey_code,
                    defaults={'name': survey_title, 'description': 'Encuesta cargada desde Excel.'}
                )
                surveys_cache[survey_title] = survey
                if created:
                    status_callback('info', f"Encuesta '{survey.name}' creada.")
            survey = surveys_cache[survey_title]

            if survey.id not in sections_cache:
                section, created = Section.objects.get_or_create(
                    survey=survey,
                    order=1,
                    defaults={'title': 'Sección Principal'}
                )
                sections_cache[survey.id] = section
                if created:
                    status_callback('info', f"Sección 'Sección Principal' creada para '{survey.name}'.")
            section = sections_cache[survey.id]

            question_text = row['text'].strip()
            question_type = row['type'].strip().lower()
            question_order = int(row['order'])
            
            type_mapping = {
                'radio': (QuestionType.SINGLE, SingleChoiceDisplayType.RADIO),
                'select': (QuestionType.SINGLE, SingleChoiceDisplayType.SELECT),
                'text': (QuestionType.TEXT, None),
                'number': (QuestionType.INTEGER, None),
                'textarea': (QuestionType.TEXT, None),
                'multi': (QuestionType.MULTI, None),
                'date': (QuestionType.DATE, None),
                'boolean': (QuestionType.BOOL, None),
            }

            q_type, display_type = type_mapping.get(question_type, (QuestionType.TEXT, None))

            question_code = slugify(f"{question_text[:40]}-{question_order}")

            question_defaults = {
                'text': question_text,
                'qtype': q_type,
                'order': question_order,
                'required': str(row.get('required', 'True')).strip().lower() in ['true', '1', 'yes'],
                'help_text': str(row.get('help_text', '')),
            }
            if display_type:
                question_defaults['single_choice_display'] = display_type

            question, created = Question.objects.update_or_create(
                section=section,
                code=question_code,
                defaults=question_defaults
            )
            
            questions_cache[question_text] = question

            if created:
                status_callback('info', f"  - Pregunta '{question.text}' creada.")
            else:
                status_callback('info', f"  - Pregunta '{question.text}' actualizada.")

            if pd.notna(row.get('choices')):
                choices_str = str(row['choices'])
                Option.objects.filter(question=question).delete()
                for i, choice_text in enumerate(choices_str.split(',')):
                    choice_text = choice_text.strip()
                    if choice_text:
                        Option.objects.create(
                            question=question,
                            code=slugify(f"{question.code}-{choice_text[:20]}"),
                            label=choice_text,
                            order=i + 1
                        )
                status_callback('info', f"    - Opciones actualizadas para '{question.text}'.")

        except Exception as e:
            status_callback('error', f"Error procesando la fila {index + 2}: {e}")
            continue

    status_callback('info', "\nResolviendo dependencias entre preguntas...")
    for index, row in df.iterrows():
        if pd.notna(row.get('depends_on_question')):
            dependent_question_text = row['text'].strip()
            parent_question_text = row['depends_on_question'].strip()

            dependent_question = questions_cache.get(dependent_question_text)
            parent_question = questions_cache.get(parent_question_text)

            if not dependent_question or not parent_question:
                status_callback('warning', f"ADVERTENCIA: No se pudo resolver la dependencia para '{dependent_question_text}'. Pregunta o padre no encontrados.")
                continue
            
            # Asignar la pregunta padre
            dependent_question.depends_on = parent_question

            # Caso 1: Dependencia de Opción (radio/select)
            if pd.notna(row.get('depends_on_option')):
                trigger_option_text = str(row['depends_on_option']).strip()
                try:
                    trigger_option = Option.objects.get(question=parent_question, label=trigger_option_text)
                    dependent_question.depends_on_option = trigger_option
                    dependent_question.depends_on_value_min = None # Limpiar el otro tipo de dependencia
                    dependent_question.depends_on_value_max = None # Limpiar el otro tipo de dependencia
                    dependent_question.save()
                    status_callback('info', f"  - Dependencia de opción establecida: '{dependent_question.text}' depende de '{parent_question.text}' = '{trigger_option.label}'.")
                except Option.DoesNotExist:
                    status_callback('warning', f"ADVERTENCIA: No se encontró la opción '{trigger_option_text}' para '{parent_question_text}'.")
                except Exception as e:
                    status_callback('error', f"Error al establecer dependencia de opción para '{dependent_question.text}': {e}")
            
            # Caso 2: Dependencia de Valor Numérico
            elif pd.notna(row.get('depends_on_value_min')) or pd.notna(row.get('depends_on_value_max')):
                min_val = row.get('depends_on_value_min')
                max_val = row.get('depends_on_value_max')
                
                dependent_question.depends_on_option = None # Limpiar el otro tipo de dependencia
                dependent_question.depends_on_value_min = min_val if pd.notna(min_val) else None
                dependent_question.depends_on_value_max = max_val if pd.notna(max_val) else None
                dependent_question.save()
                status_callback('info', f"  - Dependencia numérica establecida: '{dependent_question.text}' depende de '{parent_question.text}' (Rango: {min_val}-{max_val}).")


    status_callback('success', "\n¡Proceso de carga finalizado con éxito!")

@login_required
def survey_upload_view(request):
    if request.method == 'POST':
        form = SurveyUploadForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = request.FILES['excel_file']
            
            # Usamos una función lambda para que los mensajes se agreguen al request
            status_callback = lambda tag, msg: messages.add_message(request, getattr(messages, tag.upper(), messages.INFO), msg)
            
            _process_survey_excel(excel_file, status_callback)
            
            return redirect(request.path) # Redirige a la misma página para mostrar los mensajes
    else:
        form = SurveyUploadForm()

    return render(request, 'surveys/survey_upload.html', {'form': form})


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
                respondent_form = ResponseSetForm(request.POST, document_types=DOCUMENT_TYPES, user=request.user)
                context = {
                    'survey': survey,
                    'respondent_form': respondent_form,
                    'is_respondent_step': True,
                    'consent_error': 'Debes aceptar la cláusula de protección de datos para continuar.',
                    'data_protection_clause_text': settings.DATA_PROTECTION_CLAUSE_TEXT,
                }
                return render(request, 'surveys/survey_fill_steps.html', context)

            respondent_form = ResponseSetForm(request.POST, document_types=DOCUMENT_TYPES, user=request.user)
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
                    'data_protection_clause_text': settings.DATA_PROTECTION_CLAUSE_TEXT,
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
                                'user': request.user if request.user.is_authenticated else None,
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
                    'data_protection_clause_text': settings.DATA_PROTECTION_CLAUSE_TEXT,
                }
                return render(request, 'surveys/survey_fill_steps.html', context)

    # GET request logic
    if is_respondent_step:
        respondent_form = ResponseSetForm(initial=request.session.get('respondent_data', {}), document_types=DOCUMENT_TYPES, user=request.user)
        context = {
            'survey': survey,
            'respondent_form': respondent_form,
            'is_respondent_step': True,
            'data_protection_clause_text': settings.DATA_PROTECTION_CLAUSE_TEXT,
        }
    else:
        current_section_idx = int(request.GET.get('section', 0))
        if not sections.exists() or current_section_idx >= len(sections):
            return redirect('surveys:list')
        
        current_section = sections[current_section_idx]

        # Lógica para copiar respuestas de preguntas anteriores
        initial_data = request.session.get('survey_answers', {}).get(str(current_section.pk), {})
        for question in current_section.questions.all():
            if question.copy_from:
                source_field_name = question.copy_from
                copied_value = None

                # Buscar en los datos del encuestado
                if source_field_name in request.session.get('respondent_data', {}):
                    copied_value = request.session['respondent_data'][source_field_name]
                else:
                    # Buscar en las respuestas de otras preguntas
                    for section_id, answers in request.session.get('survey_answers', {}).items():
                        if source_field_name in answers:
                            copied_value = answers[source_field_name]
                            break
                
                if copied_value is not None:
                    initial_data[f'question_{question.pk}'] = copied_value

        AnswersForm = build_answers_form_for_section(current_section)
        answers_form = AnswersForm(initial=initial_data)
        context = {
            'survey': survey,
            'section': current_section,
            'answers_form': answers_form,
            'current_section_idx': current_section_idx,
            'total_sections': len(sections),
            'is_respondent_step': False,
            'data_protection_clause_text': settings.DATA_PROTECTION_CLAUSE_TEXT,
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

def get_question_dependency_data(request):
    question_id = request.GET.get('question_id')
    if not question_id:
        return JsonResponse({'error': 'No question_id provided'}, status=400)
    try:
        question = Question.objects.get(pk=question_id)
        data = {
            'qtype': question.qtype,
            'options': []
        }
        if question.qtype in [QuestionType.SINGLE, QuestionType.MULTI]:
            data['options'] = list(question.options.values('id', 'label'))
        
        return JsonResponse(data)
    except Question.DoesNotExist:
        return JsonResponse({'error': 'Question not found'}, status=404)