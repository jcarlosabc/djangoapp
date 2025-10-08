from django import forms
from django.forms import ModelChoiceField, ModelMultipleChoiceField
from .models import Question, Option, QuestionType, Municipio, Ubicacion, Interviewer # Added Interviewer

class ResponseSetForm(forms.Form):
    identificacion = forms.CharField(max_length=30, label="Identificación")
    document_type = forms.ChoiceField(choices=[], label="Tipo de Documento")
    full_name = forms.CharField(max_length=200, label="Nombre Completo", required=False)
    email = forms.EmailField(label="Correo Electrónico", required=False)
    phone = forms.CharField(max_length=30, label="Teléfono", required=False)
    interviewer = forms.ModelChoiceField(
        queryset=Interviewer.objects.all(),
        label="Entrevistador",
        required=False,
        empty_label="Selecciona un entrevistador"
    )

    def __init__(self, *args, **kwargs):
        document_types = kwargs.pop("document_types", [])
        super().__init__(*args, **kwargs)
        self.fields["document_type"].choices = document_types

class AnswersForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.Textarea, forms.DateInput, forms.Select)):
                field.widget.attrs.update({"class": "form-control"})
            elif isinstance(field.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
                field.widget.attrs.update({"class": "form-check-input"})

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

    return type(f"AnswersFormForSection{section.pk}", (forms.Form,), fields)
