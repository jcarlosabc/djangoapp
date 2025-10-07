
from django import forms
from django.core.exceptions import ValidationError
from .models import ResponseSet, Survey, QuestionType

class RespondentForm(forms.ModelForm):
    class Meta:
        model = ResponseSet
        fields = ["identificacion", "document_type", "full_name", "email", "phone", "interviewer"]

    def __init__(self, *args, survey: Survey, show_interviewer: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self.survey = survey
        if not show_interviewer:
            self.fields.pop("interviewer", None)
        self.fields["identificacion"].required = True
        self.fields["document_type"].required = True

        for _, field in self.fields.items():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " w-full border rounded px-3 py-2").strip()

    def clean(self):
        cleaned = super().clean()
        ident = cleaned.get("identificacion")
        doctype = cleaned.get("document_type")
        if ident and doctype:
            exists = ResponseSet.objects.filter(
                survey=self.survey, identificacion=ident, document_type=doctype
            ).exists()
            if exists:
                raise ValidationError("Esta persona ya respondió esta encuesta (no se permite duplicidad).")
        return cleaned
    

def build_answers_form_for_section(section):
    """
    Devuelve una clase de Form con campos dinámicos para la sección dada.
    Se usa type(...) para que Django registre base_fields al crear la clase.
    """
    fields = {}

    for q in section.questions.all().prefetch_related("options"):
        name = f"q_{q.id}"
        common = {"label": q.text, "required": q.required, "help_text": q.help_text}

        if q.qtype in (QuestionType.SINGLE, QuestionType.LIKERT):
            choices = [(o.id, o.label) for o in q.options.all()]
            field = forms.ChoiceField(choices=choices, widget=forms.RadioSelect, **common)

        elif q.qtype == QuestionType.MULTI:
            choices = [(o.id, o.label) for o in q.options.all()]
            field = forms.MultipleChoiceField(choices=choices, widget=forms.CheckboxSelectMultiple, **common)
            if q.max_choices:
                def _limit_max(value, maxc=q.max_choices, code=q.code):
                    if len(value) > maxc:
                        raise ValidationError(f"'{code}' admite máximo {maxc} selecciones.")
                field.validators.append(_limit_max)

        elif q.qtype == QuestionType.TEXT:
            field = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), **common)

        elif q.qtype == QuestionType.INTEGER:
            field = forms.IntegerField(**common)

        elif q.qtype == QuestionType.DECIMAL:
            field = forms.DecimalField(max_digits=12, decimal_places=2, **common)

        elif q.qtype == QuestionType.BOOL:
            field = forms.BooleanField(**common)

        elif q.qtype == QuestionType.DATE:
            field = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), **common)

        else:
            field = forms.CharField(**common)

        field.question = q

        # Estilos para inputs normales
        if not isinstance(field.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
            css = field.widget.attrs.get("class", "")
            width_class = "w-full"
            if q.qtype in (QuestionType.INTEGER, QuestionType.DECIMAL, QuestionType.DATE):
                width_class = "w-auto"
            field.widget.attrs["class"] = (css + f" {width_class} border rounded px-3 py-2").strip()

        fields[name] = field

    DynamicForm = type(f"AnswersForm_Section_{section.id}", (forms.Form,), fields)
    return DynamicForm


def build_answers_form_for_section_bk(section):
    class _AnswersForm(forms.Form):
        pass

    for q in section.questions.all().prefetch_related("options"):
        name = f"q_{q.id}"
        common = {"label": q.text, "required": q.required, "help_text": q.help_text}

        if q.qtype in (QuestionType.SINGLE, QuestionType.LIKERT):
            choices = [(o.id, o.label) for o in q.options.all()]
            field = forms.ChoiceField(choices=choices, widget=forms.RadioSelect, **common)

        elif q.qtype == QuestionType.MULTI:
            choices = [(o.id, o.label) for o in q.options.all()]
            field = forms.MultipleChoiceField(choices=choices, widget=forms.CheckboxSelectMultiple, **common)
            if q.max_choices:
                def _limit_max(value, maxc=q.max_choices, code=q.code):
                    if len(value) > maxc:
                        raise ValidationError(f"'{code}' admite máximo {maxc} selecciones.")
                field.validators.append(_limit_max)

        elif q.qtype == QuestionType.TEXT:
            field = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), **common)

        elif q.qtype == QuestionType.INTEGER:
            field = forms.IntegerField(**common)

        elif q.qtype == QuestionType.DECIMAL:
            field = forms.DecimalField(max_digits=12, decimal_places=2, **common)

        elif q.qtype == QuestionType.BOOL:
            field = forms.BooleanField(**common)

        elif q.qtype == QuestionType.DATE:
            field = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), **common)

        else:
            field = forms.CharField(**common)

        if not isinstance(field.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (css + " w-full border rounded px-3 py-2").strip()

        setattr(_AnswersForm, name, field)

    return _AnswersForm
