
import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify
from surveys.models import Survey, Section, Question, Option, QuestionType, SingleChoiceDisplayType, SingleChoiceDisplayType

class Command(BaseCommand):
    help = 'Carga una encuesta completa desde un archivo Excel (.xlsx)'

    def add_arguments(self, parser):
        parser.add_argument('excel_file', type=str, help='La ruta absoluta al archivo Excel.')

    def handle(self, *args, **options):
        excel_file_path = options['excel_file']

        try:
            df = pd.read_excel(excel_file_path)
        except FileNotFoundError:
            raise CommandError(f'El archivo "{excel_file_path}" no fue encontrado.')
        except Exception as e:
            raise CommandError(f"Error al leer el archivo Excel: {e}")

        # Validar columnas necesarias
        required_columns = ['survey_title', 'text', 'type', 'order']
        if not all(col in df.columns for col in required_columns):
            raise CommandError(f"El archivo Excel debe contener las siguientes columnas: {', '.join(required_columns)}")

        # Cache para no buscar en la BD repetidamente
        surveys_cache = {}
        sections_cache = {}
        questions_cache = {}

        self.stdout.write(self.style.SUCCESS("Iniciando el proceso de carga de la encuesta..."))

        for index, row in df.iterrows():
            try:
                # --- Obtener o crear la Encuesta (Survey) ---
                survey_title = row['survey_title'].strip()
                if survey_title not in surveys_cache:
                    survey_code = slugify(survey_title)
                    survey, created = Survey.objects.get_or_create(
                        code=survey_code,
                        defaults={'name': survey_title, 'description': 'Encuesta cargada desde Excel.'}
                    )
                    surveys_cache[survey_title] = survey
                    if created:
                        self.stdout.write(f"Encuesta '{survey.name}' creada.")
                survey = surveys_cache[survey_title]

                # --- Obtener o crear la Sección (Section) ---
                section_title = row.get('section_title', 'Sección Principal').strip()
                section_order = int(row.get('section_order', 1))
                section_key = (survey.id, section_order)

                if section_key not in sections_cache:
                    section, created = Section.objects.update_or_create(
                        survey=survey,
                        order=section_order,
                        defaults={'title': section_title}
                    )
                    sections_cache[section_key] = section
                    if created:
                        self.stdout.write(f"Sección '{section.title}' (Orden: {section.order}) creada para la encuesta '{survey.name}'.")
                section = sections_cache[section_key]

                # --- Crear la Pregunta (Question) ---
                question_text = row['text'].strip()
                question_type = row['type'].strip().lower()
                question_order = int(row['order'])
                
                # Mapeo de tipos de Excel a tipos de modelo
                type_mapping = {
                    'radio': (QuestionType.SINGLE, SingleChoiceDisplayType.RADIO),
                    'select': (QuestionType.SINGLE, SingleChoiceDisplayType.SELECT),
                    'text': (QuestionType.TEXT, None),
                    'number': (QuestionType.INTEGER, None),
                    'textarea': (QuestionType.TEXT, None), # Asumimos que textarea es un text más grande
                    'multi': (QuestionType.MULTI, None),
                    'date': (QuestionType.DATE, None),
                    'boolean': (QuestionType.BOOL, None),
                }

                if question_type not in type_mapping:
                    self.stdout.write(self.style.WARNING(f"ADVERTENCIA: Tipo de pregunta '{question_type}' en la fila {index+2} no es válido. Se usará 'text' por defecto."))
                    q_type, display_type = QuestionType.TEXT, None
                else:
                    q_type, display_type = type_mapping[question_type]

                question_code = slugify(f"{question_text[:40]}-{question_order}")

                question_defaults = {
                    'text': question_text,
                    'qtype': q_type,
                    'order': question_order,
                    'required': row.get('required', 'true').strip().lower() in ['true', '1', 'yes'],
                    'help_text': row.get('help_text', ''),
                }
                if display_type:
                    question_defaults['single_choice_display'] = display_type

                question, created = Question.objects.update_or_create(
                    section=section,
                    code=question_code,
                    defaults=question_defaults
                )
                
                # Guardar en cache para resolver dependencias
                questions_cache[question_text] = question

                if created:
                    self.stdout.write(f"  - Pregunta '{question.text}' creada.")
                else:
                    self.stdout.write(f"  - Pregunta '{question.text}' actualizada.")

                # --- Crear Opciones (Options) si existen ---
                if pd.notna(row.get('choices')):
                    choices_str = str(row['choices'])
                    # Limpiar opciones existentes antes de crear nuevas
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
                    self.stdout.write(f"    - Opciones creadas/actualizadas para '{question.text}'.")

            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error procesando la fila {index + 2}: {e}"))
                continue

        # --- Segunda pasada para resolver dependencias ---
        self.stdout.write(self.style.SUCCESS("
Resolviendo dependencias entre preguntas..."))
        for index, row in df.iterrows():
            if pd.notna(row.get('depends_on_question')):
                dependent_question_text = row['text'].strip()
                parent_question_text = row['depends_on_question'].strip()

                dependent_question = questions_cache.get(dependent_question_text)
                parent_question = questions_cache.get(parent_question_text)

                if not dependent_question or not parent_question:
                    self.stdout.write(self.style.WARNING(f"ADVERTENCIA: No se pudo resolver la dependencia para '{dependent_question_text}'. Pregunta o padre no encontrados."))
                    continue
                
                dependent_question.depends_on = parent_question

                # Caso 1: Dependencia de Opción
                if pd.notna(row.get('depends_on_option')):
                    trigger_option_text = str(row['depends_on_option']).strip()
                    try:
                        trigger_option = Option.objects.get(question=parent_question, label=trigger_option_text)
                        dependent_question.depends_on_option = trigger_option
                        dependent_question.depends_on_value_min = None
                        dependent_question.depends_on_value_max = None
                        dependent_question.save()
                        self.stdout.write(f"  - Dependencia de opción: '{dependent_question.text}' depende de '{parent_question.text}' = '{trigger_option.label}'.")
                    except Option.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f"ADVERTENCIA: No se encontró la opción '{trigger_option_text}' para '{parent_question_text}'."))
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Error al establecer dependencia de opción para '{dependent_question.text}': {e}"))
                
                # Caso 2: Dependencia de Valor Numérico
                elif pd.notna(row.get('depends_on_value_min')) or pd.notna(row.get('depends_on_value_max')):
                    min_val = row.get('depends_on_value_min')
                    max_val = row.get('depends_on_value_max')
                    
                    dependent_question.depends_on_option = None
                    dependent_question.depends_on_value_min = min_val if pd.notna(min_val) else None
                    dependent_question.depends_on_value_max = max_val if pd.notna(max_val) else None
                    dependent_question.save()
                    self.stdout.write(f"  - Dependencia numérica: '{dependent_question.text}' depende de '{parent_question.text}' (Rango: {min_val}-{max_val}).")

        self.stdout.write(self.style.SUCCESS("
¡Proceso de carga finalizado con éxito!"))
