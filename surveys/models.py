from django.db import models
from django.db.models import Q, CheckConstraint
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
    UBICACION = "ubicacion", "Selección de Ubicación"

class SingleChoiceDisplayType(models.TextChoices):
    RADIO = "radio", "Botones de radio"
    SELECT = "select", "Lista desplegable"

class Municipio(models.Model):
    nombre = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.nombre

class Ubicacion(models.Model):
    municipio = models.ForeignKey(Municipio, on_delete=models.CASCADE, related_name='ubicaciones')
    codigo = models.CharField(max_length=50)
    nombre = models.CharField(max_length=255)
    loc = models.CharField(max_length=255)
    zona = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.municipio.nombre} - {self.nombre}"

    class Meta:
        verbose_name = "Ubicación"
        verbose_name_plural = "Ubicaciones"
        unique_together = ('municipio', 'codigo')
        ordering = ['municipio', 'nombre']

class Question(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="questions")
    code = models.SlugField(max_length=80)
    text = models.TextField()
    help_text = models.TextField(blank=True)
    qtype = models.CharField(max_length=10, choices=QuestionType.choices, default=QuestionType.TEXT)
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=1)
    max_choices = models.PositiveIntegerField(default=0, help_text="0 = sin límite")
    # New field for linking to Barrio model
    ubicaciones = models.ManyToManyField(Ubicacion, blank=True, related_name="questions")

    single_choice_display = models.CharField(
        max_length=10,
        choices=SingleChoiceDisplayType.choices,
        default=SingleChoiceDisplayType.RADIO,
        help_text="Solo para preguntas de opción única (single)"
    )

    depends_on = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dependent_questions',
        help_text="La pregunta de la que esta depende"
    )
    depends_on_option = models.ForeignKey(
        'surveys.Option',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggering_questions',
        help_text="La opción que activa esta pregunta"
    )

    depends_on_value_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Valor mínimo para activar la pregunta (para respuestas numéricas)")
    depends_on_value_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Valor máximo para activar la pregunta (para respuestas numéricas)")

    copy_from = models.CharField(max_length=100, blank=True, help_text="Nombre del campo del cual copiar la respuesta (ej. 'identificacion' o 'question_123').")
    copy_text_from = models.BooleanField(default=False, help_text="Si se marca, el texto de la pregunta se copiará del campo seleccionado.")

    min_value = models.IntegerField(null=True, blank=True, help_text="Valor mínimo para preguntas de tipo entero.")
    max_value = models.IntegerField(null=True, blank=True, help_text="Valor máximo para preguntas de tipo entero.")
    other_text_label = models.CharField(
        max_length=100,
        blank=True,
        default="Especifique",
        help_text="Etiqueta para el campo de texto 'otro'."
    )

    def clean(self):
        super().clean()
        # Ensure that only one option can be marked as 'other_trigger'
        if self.pk and self.options.filter(is_other_trigger=True).count() > 1:
            from django.core.exceptions import ValidationError
            raise ValidationError("Solo una opción por pregunta puede ser marcada como la opción 'Otro'.")


    class Meta:
        unique_together = ("section", "code")
        ordering = ["section__order", "order"]
        constraints = [
            CheckConstraint(
                check=Q(depends_on_option__isnull=True) | (Q(depends_on_value_min__isnull=True) & Q(depends_on_value_max__isnull=True)),
                name='option_or_value_dependency'
            )
        ]
    def __str__(self): return f"{self.section} · {self.code}"

class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    code = models.SlugField(max_length=80)
    label = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1)
    numeric_value = models.IntegerField(null=True, blank=True,
                                        validators=[MinValueValidator(0), MaxValueValidator(10)])
    is_other_trigger = models.BooleanField("Es la opción 'Otro'", default=False, help_text="Si se marca, esta opción mostrará un campo de texto adicional.")

    def clean(self):
        super().clean()
        if self.is_other_trigger and self.question.qtype not in [QuestionType.SINGLE, QuestionType.MULTI]:
            from django.core.exceptions import ValidationError
            raise ValidationError("La opción 'Otro' solo es aplicable a preguntas de opción única o múltiple.")

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
    # New field to store selected Barrio(s) for BARRIO type questions
    selected_ubicaciones = models.ManyToManyField(Ubicacion, blank=True, related_name="answers")

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
            or (self.pk and self.selected_ubicaciones.exists()) # Check for selected ubicaciones
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
        # Validation for UBICACION type questions
        if q.qtype == QuestionType.UBICACION:
            if q.required and not self.selected_ubicaciones.exists():
                raise ValidationError(f"La pregunta '{q.code}' requiere la selección de al menos una ubicación.")
            # If max_choices is used for UBICACION type
            if q.max_choices and self.pk and self.selected_ubicaciones.count() > q.max_choices:
                raise ValidationError(f"'{q.code}' admite máximo {q.max_choices} selecciones de ubicaciones.")


# New model for .xlsx file handling
class UbicacionListFile(models.Model):
    name = models.CharField(max_length=255, unique=True)
    file = models.FileField(upload_to='ubicacion_list_files/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
