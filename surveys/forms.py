from django import forms
from .models import ResponseSet, Answer, DOCUMENT_TYPES, Question, QuestionType, Interviewer, SingleChoiceDisplayType
from django.contrib.auth.models import User

class SurveyUploadForm(forms.Form):
    excel_file = forms.FileField(
        label="Archivo Excel",
        help_text="Sube un archivo .xlsx con la estructura de la encuesta.",
        widget=forms.ClearableFileInput(attrs={'class': 'mt-1 block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none'}),
        validators=[
            lambda file: file.name.endswith('.xlsx') or forms.ValidationError("El archivo debe ser .xlsx")
        ]
    )

class ResponseForm(forms.ModelForm):
    class Meta:
        model = ResponseSet
        fields = []


class ResponseSetForm(forms.Form):
    text_input_classes = 'mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md text-sm shadow-sm placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500'
    identificacion = forms.CharField(max_length=30, label="Identificación", widget=forms.TextInput(attrs={'class': text_input_classes}))
    document_type = forms.ChoiceField(choices=[], label="Tipo de Documento", widget=forms.Select(attrs={'class': text_input_classes}))
    full_name = forms.CharField(max_length=200, label="Nombre Completo", required=False, widget=forms.TextInput(attrs={'class': text_input_classes}))
    email = forms.EmailField(label="Correo Electrónico", required=False, widget=forms.EmailInput(attrs={'class': text_input_classes}))
    phone = forms.CharField(max_length=30, label="Teléfono", required=False, widget=forms.TextInput(attrs={'class': text_input_classes}))
    interviewer = forms.ModelChoiceField(
        queryset=Interviewer.objects.all(),
        label="Entrevistador",
        required=False,
        empty_label="Selecciona un entrevistador",
        widget=forms.Select(attrs={'class': text_input_classes})
    )

    def __init__(self, *args, **kwargs):
        document_types = kwargs.pop("document_types", [])
        user = kwargs.pop("user", None) # Get user from kwargs
        super().__init__(*args, **kwargs)
        self.fields["document_type"].choices = document_types

        # If user is not authenticated, remove the interviewer field
        if user and not user.is_authenticated:
            if 'interviewer' in self.fields:
                del self.fields['interviewer']

class QuestionAdminForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Check if the form is bound to data (i.e., a POST request)
        if self.is_bound and self.data.get('depends_on'):
            try:
                # Get the ID of the parent question from the submitted data
                depends_on_id = int(self.data.get('depends_on'))
                # Update the queryset for the depends_on_option field
                self.fields['depends_on_option'].queryset = Option.objects.filter(question_id=depends_on_id)
            except (ValueError, TypeError):
                # Handle cases where depends_on is not a valid ID
                self.fields['depends_on_option'].queryset = Option.objects.none()

    class Meta:
        model = Question
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        depends_on_question = cleaned_data.get("depends_on")
        depends_on_option = cleaned_data.get("depends_on_option")
        min_val = cleaned_data.get("depends_on_value_min")
        max_val = cleaned_data.get("depends_on_value_max")

        if not depends_on_question:
            return cleaned_data

        # Enforce that option and value dependencies are mutually exclusive
        if depends_on_option and (min_val is not None or max_val is not None):
            raise forms.ValidationError(
                "Una pregunta no puede depender de una opción y de un rango de valores al mismo tiempo.",
                code='invalid_dependency_mix'
            )

        # Validate option-based dependency
        if depends_on_option:
            if depends_on_question.qtype not in [QuestionType.SINGLE, QuestionType.MULTI]:
                self.add_error('depends_on_question', "La dependencia de opción solo puede apuntar a preguntas de opción única o múltiple.")
            elif not depends_on_question.options.filter(pk=depends_on_option.pk).exists():
                self.add_error('depends_on_option', "La opción seleccionada no pertenece a la pregunta de la que depende.")

        # Validate value-based dependency
        if min_val is not None or max_val is not None:
            if depends_on_question.qtype not in [QuestionType.INTEGER, QuestionType.DECIMAL]:
                self.add_error('depends_on_question', "La dependencia de valor solo puede apuntar a preguntas de tipo numérico (entero o decimal).")
            if min_val is not None and max_val is not None and min_val > max_val:
                self.add_error('depends_on_value_max', "El valor máximo no puede ser menor que el valor mínimo.")

        return cleaned_data

class AnswersForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        text_input_classes = 'mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md text-sm shadow-sm placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500'
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.DateInput, forms.EmailInput, forms.NumberInput, forms.URLInput, forms.Select)):
                attrs = field.widget.attrs
                attrs['class'] = text_input_classes
                if isinstance(field.widget, forms.Textarea):
                    attrs['rows'] = 2
            elif isinstance(field.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
                # Styling for these is handled in the template
                pass

def build_answers_form_for_section(section):
    fields = {}
    questions = section.questions.prefetch_related('options', 'depends_on').all()
    for q in questions:
        field_name = f"question_{q.pk}"
        field_kwargs = {
            'label': q.text,
            'help_text': q.help_text,
            'required': q.required,
        }

        if q.qtype == QuestionType.TEXT:
            field = forms.CharField(
                **field_kwargs,
                widget=forms.Textarea if q.max_choices == 0 else forms.TextInput,
            )
        elif q.qtype == QuestionType.INTEGER:
            widget_attrs = {}
            if q.min_value is not None:
                field_kwargs['min_value'] = q.min_value
                widget_attrs['min'] = q.min_value
            if q.max_value is not None:
                field_kwargs['max_value'] = q.max_value
                widget_attrs['max'] = q.max_value
            
            field_kwargs['widget'] = forms.NumberInput(attrs=widget_attrs)
            field = forms.IntegerField(**field_kwargs)
        elif q.qtype == QuestionType.DECIMAL:
            field = forms.DecimalField(**field_kwargs)
        elif q.qtype == QuestionType.BOOL:
            field = forms.BooleanField(**field_kwargs, widget=forms.CheckboxInput)
        elif q.qtype == QuestionType.DATE:
            field = forms.DateField(**field_kwargs, widget=forms.DateInput(attrs={'type': 'date'}))
        elif q.qtype in [QuestionType.SINGLE, QuestionType.MULTI, QuestionType.LIKERT]:
            choices = [(option.pk, option.label) for option in q.options.all()]
            if q.qtype == QuestionType.SINGLE or q.qtype == QuestionType.LIKERT:
                widget = forms.RadioSelect
                if q.qtype == QuestionType.SINGLE and q.single_choice_display == SingleChoiceDisplayType.SELECT:
                    widget = forms.Select
                field = forms.ChoiceField(
                    **field_kwargs,
                    choices=choices,
                    widget=widget,
                )
            elif q.qtype == QuestionType.MULTI:
                field = forms.MultipleChoiceField(
                    **field_kwargs,
                    choices=choices,
                    widget=forms.CheckboxSelectMultiple,
                )
        elif q.qtype == QuestionType.UBICACION:
            # For UBICACION, we create multiple fields. We will attach the question object to the main one.
            fields[f"{field_name}_municipio"] = ModelChoiceField(
                queryset=Municipio.objects.all(),
                label="Municipio",
                required=q.required,
                empty_label="Selecciona un municipio",
            )
            ubicacion_field = forms.ChoiceField(
                label="Barrio/Localidad",
                required=q.required,
                choices=[],
            )
            ubicacion_field.question = q # Attach question here
            fields[f"{field_name}_ubicacion"] = ubicacion_field

            fields[f"{field_name}_loc"] = forms.CharField(
                label="LOC",
                required=False,
                widget=forms.TextInput(attrs={'readonly': 'readonly'}),
            )
            fields[f"{field_name}_zona"] = forms.CharField(
                label="ZONA",
                required=False,
                widget=forms.TextInput(attrs={'readonly': 'readonly'}),
            )
            continue # Skip the generic field attachment for this type
        else:
            continue # Skip unknown question types

        field.question = q
        fields[field_name] = field

    class DynamicAnswersForm(forms.Form):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            text_input_classes = 'mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md text-sm shadow-sm placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500'
            for field_name, field in self.fields.items():
                if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.DateInput, forms.EmailInput, forms.NumberInput, forms.URLInput, forms.Select)):
                    attrs = field.widget.attrs
                    attrs['class'] = text_input_classes
                    if isinstance(field.widget, forms.Textarea):
                        attrs['rows'] = 2
                elif isinstance(field.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
                    # Styling for these is handled in the template
                    pass

            # Dynamic choices for ubicacion fields
            for q in section.questions.all():
                if q.qtype == QuestionType.UBICACION:
                    field_name = f"question_{q.pk}"
                    municipio_field_name = f"{field_name}_municipio"
                    ubicacion_field_name = f"{field_name}_ubicacion"

                    if municipio_field_name in self.fields and ubicacion_field_name in self.fields:
                        # If form is submitted, try to get municipio from data
                        if self.is_bound and self.data.get(municipio_field_name):
                            try:
                                municipio_id = int(self.data.get(municipio_field_name))
                                ubicaciones = Ubicacion.objects.filter(municipio_id=municipio_id).order_by('nombre')
                                self.fields[ubicacion_field_name].choices = [(u.pk, u.nombre) for u in ubicaciones]
                            except (ValueError, TypeError):
                                pass # Handle cases where municipio_id is not a valid integer

    DynamicAnswersForm.base_fields = fields
    return DynamicAnswersForm
