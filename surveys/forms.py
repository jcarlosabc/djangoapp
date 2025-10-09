from django import forms
from django.forms import ModelChoiceField, ModelMultipleChoiceField
from .models import Question, Option, QuestionType, Municipio, Ubicacion, Interviewer # Added Interviewer

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

class AnswersForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        text_input_classes = 'mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md text-sm shadow-sm placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500'
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.DateInput, forms.EmailInput, forms.NumberInput, forms.URLInput, forms.Select)):
                attrs = field.widget.attrs
                attrs['class'] = text_input_classes
                if isinstance(field.widget, forms.Textarea):
                    attrs['rows'] = 4
            elif isinstance(field.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
                # Styling for these is handled in the template
                pass

def build_answers_form_for_section(section):
    fields = {}
    for q in section.questions.all():
        field_name = f"question_{q.pk}"
        if q.qtype == QuestionType.TEXT:
            fields[field_name] = forms.CharField(
                label=q.text,
                help_text=q.help_text,
                required=q.required,
                widget=forms.Textarea if q.max_choices == 0 else forms.TextInput, # max_choices 0 for textarea
            )
        elif q.qtype == QuestionType.INTEGER:
            fields[field_name] = forms.IntegerField(
                label=q.text,
                help_text=q.help_text,
                required=q.required,
            )
        elif q.qtype == QuestionType.DECIMAL:
            fields[field_name] = forms.DecimalField(
                label=q.text,
                help_text=q.help_text,
                required=q.required,
            )
        elif q.qtype == QuestionType.BOOL:
            fields[field_name] = forms.BooleanField(
                label=q.text,
                help_text=q.help_text,
                required=q.required,
                widget=forms.CheckboxInput,
            )
        elif q.qtype == QuestionType.DATE:
            fields[field_name] = forms.DateField(
                label=q.text,
                help_text=q.help_text,
                required=q.required,
                widget=forms.DateInput(attrs={'type': 'date'}),
            )
        elif q.qtype in [QuestionType.SINGLE, QuestionType.MULTI, QuestionType.LIKERT]:
            choices = [(option.pk, option.label) for option in q.options.all()]
            if q.qtype == QuestionType.SINGLE or q.qtype == QuestionType.LIKERT:
                fields[field_name] = forms.ChoiceField(
                    label=q.text,
                    help_text=q.help_text,
                    required=q.required,
                    choices=choices,
                    widget=forms.RadioSelect,
                )
            elif q.qtype == QuestionType.MULTI:
                fields[field_name] = forms.MultipleChoiceField(
                    label=q.text,
                    help_text=q.help_text,
                    required=q.required,
                    choices=choices,
                    widget=forms.CheckboxSelectMultiple,
                )
        elif q.qtype == QuestionType.UBICACION: # New UBICACION type handling
            fields[f"{field_name}_municipio"] = ModelChoiceField(
                queryset=Municipio.objects.all(),
                label="Municipio",
                required=q.required,
                empty_label="Selecciona un municipio",
            )
            fields[f"{field_name}_ubicacion"] = forms.ChoiceField(
                label="Barrio/Localidad",
                required=q.required,
                choices=[],
            )
            fields[f"{field_name}_loc"] = forms.CharField(
                label="LOC",
                required=False, # This will be autopopulated
                widget=forms.TextInput(attrs={'readonly': 'readonly'}),
            )
            fields[f"{field_name}_zona"] = forms.CharField(
                label="ZONA",
                required=False, # This will be autopopulated
                widget=forms.TextInput(attrs={'readonly': 'readonly'}),
            )

    class DynamicAnswersForm(forms.Form):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            text_input_classes = 'mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md text-sm shadow-sm placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500'
            for field_name, field in self.fields.items():
                if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.DateInput, forms.EmailInput, forms.NumberInput, forms.URLInput, forms.Select)):
                    attrs = field.widget.attrs
                    attrs['class'] = text_input_classes
                    if isinstance(field.widget, forms.Textarea):
                        attrs['rows'] = 4
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
