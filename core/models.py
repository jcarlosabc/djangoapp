from django.db import models

# Create your models here.
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid
from decimal import Decimal

class Survey(models.Model):
    """Una encuesta (p.ej., Caracterización y Registro de Cuidadores)."""
    name = models.CharField(max_length=200, unique=True)
    code = models.SlugField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ¿Deseas exigir token en esta encuesta?
    require_token = models.BooleanField(default=False)

    def __str__(self):
        return self.name



class Section(models.Model):
    """Secciones/módulos (Sociodemográfico, Salud, Escala Zarit, etc.)."""
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1)
    #is_scala = models.BooleanField(default=False)

    class Meta:
        unique_together = ('survey', 'order')
        ordering = ['order']

    def __str__(self):
        return f"{self.survey.code} · {self.order:02d} · {self.title}"

#QuestionType

class Question(models.Model):
    """Pregunta genérica, parametrizada por tipo."""
    SINGLE = 'single'     # Opción única
    MULTI = 'multi'       # Selección múltiple
    TEXT = 'text'         # Respuesta abierta
    INTEGER = 'int'       # Entero
    DECIMAL = 'dec'       # Decimal
    BOOL = 'bool'         # Sí/No
    DATE = 'date'         # Fecha
    LIKERT = 'likert'     # Para escalas tipo Zarit (0..4)
    QUESTION_TYPES = [
        (SINGLE, 'Opción única'),
        (MULTI, 'Selección múltiple'),
        (TEXT, 'Texto'),
        (INTEGER, 'Entero'),
        (DECIMAL, 'Decimal'),
        (BOOL, 'Sí/No'),
        (DATE, 'Fecha'),
        (LIKERT, 'Likert (0..4)'),
    ]

    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='questions')
    code = models.SlugField(max_length=80)  # ej: zarit_q01, eps, ocupacion
    text = models.TextField()
    help_text = models.TextField(blank=True)
    qtype = models.CharField(max_length=10, choices=QUESTION_TYPES)
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=1)
    # Para MULTI: límite superior de selecciones (0 = sin límite)
    max_choices = models.PositiveIntegerField(default=0, help_text="0 = sin límite")

    class Meta:
        unique_together = ('section', 'code')
        ordering = ['section__order', 'order']

    def __str__(self):
        return f"{self.section} · {self.code}"


class Option(models.Model):
    """Opciones para preguntas de selección."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    code = models.SlugField(max_length=80)  # ej: nunca, casi-nunca, a-veces, a-menudo, siempre
    label = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1)
    # Para LIKERT/Zarit: valor numérico (0..4)
    numeric_value = models.IntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(10)]
    )

    class Meta:
        unique_together = ('question', 'code')
        ordering = ['order']

    def __str__(self):
        return f"{self.question.code} · {self.code}"

#no va
class AccessToken(models.Model):
    """Token de un solo uso para identificar y limitar a un envío por persona."""
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='tokens')
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    # Identificación esperada (cédula u otro) para anti-duplicado fuerte
    expected_identificacion = models.CharField(max_length=30, blank=True)
    used = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)

    def is_valid(self):
        now = timezone.now()
        return (not self.used) and (self.expires_at is None or self.expires_at > now)

    def __str__(self):
        return f"{self.survey.code}:{self.token} (used={self.used})"

#Interviewer

class ResponseSet(models.Model):
    """Un envío de encuesta (una persona/visitador)."""
    survey = models.ForeignKey(Survey, on_delete=models.PROTECT, related_name='responses')
    created_at = models.DateTimeField(auto_now_add=True)

    # Anti-duplicado: identificador único por encuesta (cédula, NIE, etc.)
    identificacion = models.CharField(max_length=30)
    # Candado de unicidad por encuesta:
    class Meta:
        unique_together = ('survey', 'identificacion')
        indexes = [
            models.Index(fields=['survey', 'identificacion']),
        ]

    # (Opcional) Datos de contacto y meta
    full_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    interviewer = models.CharField(max_length=120, blank=True)  # encuestador
    source = models.CharField(max_length=80, blank=True)  # p.ej. 'operativo_barrio_x'
    device_fingerprint = models.CharField(max_length=100, blank=True)

    #user =

    # Token usado (si la encuesta exige token)
    access_token = models.OneToOneField(
        AccessToken, null=True, blank=True, on_delete=models.SET_NULL, related_name='response'
    )

    # Puntaje Zarit pre-calculado (puedes calcular en BI, pero aquí queda cacheado)
    zarit_score = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    zarit_category = models.CharField(
        max_length=20,
        choices=[('sin', 'Sin sobrecarga'), ('leve', 'Leve/Moderada'), ('intensa', 'Intensa')],
        default='sin'
    )

    def __str__(self):
        return f"{self.survey.code} · {self.identificacion} · {self.created_at:%Y-%m-%d}"

    # --- utilidades de Zarit ---
    def compute_zarit(self):
        """Suma numeric_value de ítems tipo LIKERT asociados a Zarit."""
        total = 0
        for ans in self.answers.filter(question__qtype=Question.LIKERT):
            # si respondió por opción
            if ans.options.exists():
                total += sum(o.numeric_value or 0 for o in ans.options.all())
            # si guardaste valores directos (no usual en Likert)
            elif ans.integer_answer is not None:
                total += ans.integer_answer
        return total

    @staticmethod
    def categorize_zarit(score: int) -> str:
        # Ajusta umbrales según versión (Zarit 22 ítems estándar: 0–21 sin; 22–46 leve/moderada; ≥47 intensa)
        if score >= 47:
            return 'intensa'
        if score >= 22:
            return 'leve'
        return 'sin'

    def refresh_scores(self, save=True):
        score = self.compute_zarit()
        self.zarit_score = score
        self.zarit_category = self.categorize_zarit(score)
        if save:
            self.save(update_fields=['zarit_score', 'zarit_category'])


class Answer(models.Model):
    """Respuesta a una pregunta concreta dentro de un ResponseSet."""
    response = models.ForeignKey(ResponseSet, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name='answers')

    # Soporte multi-tipo
    text_answer = models.TextField(blank=True)
    integer_answer = models.IntegerField(null=True, blank=True)
    decimal_answer = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    bool_answer = models.BooleanField(null=True, blank=True)
    date_answer = models.DateField(null=True, blank=True)

    # Para SINGLE/MULTI/LIKERT: se guardan opciones seleccionadas
    options = models.ManyToManyField(Option, blank=True, related_name='selected_in')

    class Meta:
        unique_together = ('response', 'question')

    def __str__(self):
        return f"{self.response} · {self.question.code}"

    # Validaciones básicas:
    def clean(self):
        from django.core.exceptions import ValidationError
        q = self.question

        # Requeridos
        if q.required:
            has_value = (
                self.text_answer
                or self.integer_answer is not None
                or self.decimal_answer is not None
                or self.bool_answer is not None
                or self.date_answer is not None
                or self.options.exists()
            )
            if not has_value:
                raise ValidationError(f"La pregunta '{q.code}' es obligatoria.")

        # Consistencia por tipo
        if q.qtype in (Question.SINGLE, Question.LIKERT):
            if self.options.count() > 1:
                raise ValidationError(f"'{q.code}' admite solo una opción.")
        if q.qtype == Question.MULTI and q.max_choices and self.options.count() > q.max_choices:
            raise ValidationError(f"'{q.code}' admite máximo {q.max_choices} selecciones.")
        if q.qtype == Question.LIKERT:
            # Asegura que las opciones tengan numeric_value definido
            for o in self.options.all():
                if o.numeric_value is None:
                    raise ValidationError(f"Opción '{o.code}' de '{q.code}' no tiene valor numérico.")
