
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

DOCUMENT_TYPES = [
    ("C.C", "Cédula de Ciudadanía"),
    ("T.I", "Tarjeta de Identidad"),
    ("R.E", "Registro Civil"),
    ("C.E", "Cédula de Extranjería"),
    ("NIT", "Número de Identificación Tributaria"),
    ("PPT", "Permiso por Protección Temporal"),
    ("PA", "Pasaporte"),
    ("T.E", "Tarjeta de Extranjería"),
    ("CD", "Carnet Diplomático"),
    ("SP", "Salvoconducto de Permanencia"),
    ("P.E.P", "Permiso Especial de Permanencia"),
]

class Survey(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    code = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    require_token = models.BooleanField(default=False)
    def __str__(self): return self.name

class Section(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1)
    class Meta:
        unique_together = ("survey", "order")
        ordering = ["order"]
    def __str__(self): return f"{self.survey.code} · {self.order:02d} · {self.title}"

class QuestionType(models.TextChoices):
    SINGLE = "single", "Opción única"
    MULTI  = "multi",  "Selección múltiple"
    TEXT   = "text",   "Texto"
    INTEGER= "int",    "Entero"
    DECIMAL= "dec",    "Decimal"
    BOOL   = "bool",   "Sí/No"
    DATE   = "date",   "Fecha"
    LIKERT = "likert", "Likert (0..4)"

class Question(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="questions")
    code = models.SlugField(max_length=80)
    text = models.TextField()
    help_text = models.TextField(blank=True)
    qtype = models.CharField(max_length=10, choices=QuestionType.choices, default=QuestionType.TEXT)
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=1)
    max_choices = models.PositiveIntegerField(default=0, help_text="0 = sin límite")
    class Meta:
        unique_together = ("section", "code")
        ordering = ["section__order", "order"]
    def __str__(self): return f"{self.section} · {self.code}"

class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    code = models.SlugField(max_length=80)
    label = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1)
    numeric_value = models.IntegerField(null=True, blank=True,
                                        validators=[MinValueValidator(0), MaxValueValidator(10)])
    class Meta:
        unique_together = ("question", "code")
        ordering = ["order"]
    def __str__(self): return f"{self.question.code} · {self.code}"

class Interviewer(models.Model):
    full_name = models.CharField(max_length=200)
    document_number = models.CharField(max_length=30, unique=True)
    document_type = models.CharField(max_length=5, choices=DOCUMENT_TYPES)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    def __str__(self): return f"{self.full_name} ({self.document_type} {self.document_number})"

class ResponseSet(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.PROTECT, related_name="responses")
    identificacion = models.CharField(max_length=30)
    document_type = models.CharField(max_length=5, choices=DOCUMENT_TYPES)
    full_name = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    interviewer = models.ForeignKey(Interviewer, blank=True, null=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    data_protection_accepted = models.BooleanField(default=False) # New field for data protection consent
    class Meta:
        unique_together = ("survey", "identificacion", "document_type")
        indexes = [models.Index(fields=["survey", "identificacion", "document_type"])]
    def __str__(self): return f"{self.survey.code} · {self.identificacion} · {self.created_at:%Y-%m-%d}"

class Answer(models.Model):
    response = models.ForeignKey(ResponseSet, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    text_answer = models.TextField(blank=True)
    integer_answer = models.IntegerField(null=True, blank=True)
    decimal_answer = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    bool_answer = models.BooleanField(null=True, blank=True)
    date_answer = models.DateField(null=True, blank=True)
    options = models.ManyToManyField(Option, blank=True, related_name="selected_in")
    class Meta:
        unique_together = ("response", "question")
    def __str__(self): return f"{self.response} · {self.question.code}"
    def clean(self):
        from django.core.exceptions import ValidationError
        q = self.question
        has_value = (
            (self.text_answer and str(self.text_answer).strip())
            or self.integer_answer is not None
            or self.decimal_answer is not None
            or self.bool_answer is not None
            or self.date_answer is not None
            or (self.pk and self.options.exists())
        )
        if q.required and not has_value:
            raise ValidationError(f"La pregunta '{q.code}' es obligatoria.")
        if q.qtype in (QuestionType.SINGLE, QuestionType.LIKERT):
            if self.pk and self.options.count() > 1:
                raise ValidationError(f"'{q.code}' admite solo una opción.")
        if q.qtype == QuestionType.MULTI and q.max_choices and self.pk and self.options.count() > q.max_choices:
            raise ValidationError(f"'{q.code}' admite máximo {q.max_choices} selecciones.")
        if q.qtype == QuestionType.LIKERT and self.pk:
            for o in self.options.all():
                if o.numeric_value is None:
                    raise ValidationError(f"Opción '{o.code}' en '{q.code}' no tiene valor numérico.")
