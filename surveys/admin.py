from django.contrib import admin
from django import forms
from .models import Survey, Section, Question, Option, Interviewer, ResponseSet, Answer, Municipio, Ubicacion, UbicacionListFile # Updated import
from .forms import QuestionAdminForm

class OptionInline(admin.TabularInline):
    model = Option
    extra = 1

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1

class SectionInline(admin.StackedInline):
    model = Section
    extra = 1

@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "code", "is_active", "created_at", "require_token")
    prepopulated_fields = {"code": ("name",)}
    inlines = [SectionInline]
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'code', 'is_active', 'require_token')
        }),
    )

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("survey", "title", "order")
    ordering = ("survey", "order")
    inlines = [QuestionInline]

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    form = QuestionAdminForm
    list_display = ("section", "code", "qtype", "single_choice_display", "required", "order", "max_choices", "copy_from", "min_value", "max_value")
    list_filter = ("qtype", "required", "section__survey")
    inlines = [OptionInline]
    fieldsets = (
        (None, {
            'fields': ('section', 'code', 'text', 'help_text', 'qtype', 'single_choice_display', 'required', 'order', 'max_choices', 'ubicaciones', 'min_value', 'max_value')
        }),
        ('Dependencia', {
            'fields': ('depends_on', 'depends_on_option', 'depends_on_value_min', 'depends_on_value_max'),
        }),
        ('Copia de Respuestas', {
            'fields': ('copy_from', 'copy_text_from'),
        }),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == 'copy_from':
            choices = [('', '---------')]
            # Add ResponseSetForm fields
            choices.extend([
                ('identificacion', 'Identificación (del encuestado)'),
                ('full_name', 'Nombre Completo (del encuestado)'),
                ('email', 'Correo Electrónico (del encuestado)'),
                ('phone', 'Teléfono (del encuestado)'),
            ])

            # Add all questions
            for q in Question.objects.all().order_by('section__survey__name', 'section__order', 'order'):
                choices.append((f'question_{q.pk}', f'{q.section.survey.name} / {q.section.title} / {q.text[:50]}...'))

            return forms.ChoiceField(choices=choices, required=False)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "depends_on_option":
            # Get the current object being edited
            obj_id = request.resolver_match.kwargs.get('object_id')
            if obj_id:
                try:
                    question = self.get_object(request, obj_id)
                    if question and question.depends_on:
                        kwargs["queryset"] = Option.objects.filter(question=question.depends_on)
                    else:
                        kwargs["queryset"] = Option.objects.none()
                except self.model.DoesNotExist:
                     kwargs["queryset"] = Option.objects.none()
            else:
                kwargs["queryset"] = Option.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    class Media:
        js = ('admin/js/jquery.init.js', 'admin/js/question_admin.js')

@admin.register(Interviewer)
class InterviewerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "document_type", "document_number", "phone", "email")
    search_fields = ("full_name", "document_number", "email")

class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ('question', 'text_answer', 'integer_answer', 'decimal_answer', 'bool_answer', 'date_answer', 'options_display', 'selected_ubicaciones_display') # Added selected_ubicaciones_display
    fields = ('question', 'text_answer', 'integer_answer', 'decimal_answer', 'bool_answer', 'date_answer', 'options_display', 'selected_ubicaciones_display') # Added selected_ubicaciones_display
    can_delete = False

    def options_display(self, obj):
        return ", ".join([option.label for option in obj.options.all()])
    options_display.short_description = "Opciones Seleccionadas"

    def selected_ubicaciones_display(self, obj): # New method to display selected ubicaciones
        return ", ".join([ubicacion.nombre for ubicacion in obj.selected_ubicaciones.all()])
    selected_ubicaciones_display.short_description = "Ubicaciones Seleccionadas"

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(ResponseSet)
class ResponseSetAdmin(admin.ModelAdmin):
    list_display = ("survey", "identificacion", "document_type", "user", "interviewer", "created_at")
    list_filter = ("survey", "document_type")
    search_fields = ("identificacion", "full_name", "email", "phone")
    inlines = [AnswerInline]

@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("response", "question")
    list_filter = ("question__section__survey",)

# Removed @admin.register(GeoJSONFile) and GeoJSONFileAdmin

@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(Ubicacion)
class UbicacionAdmin(admin.ModelAdmin):
    list_display = ('municipio', 'nombre', 'codigo', 'loc', 'zona')
    search_fields = ('nombre', 'codigo')
    list_filter = ('municipio',)

@admin.register(UbicacionListFile) # New admin registration
class UbicacionListFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'uploaded_at')
    search_fields = ('name',)