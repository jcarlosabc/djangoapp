
from django.contrib import admin
from .models import Survey, Section, Question, Option, Interviewer, ResponseSet, Answer

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
    list_display = ("section", "code", "qtype", "required", "order", "max_choices")
    list_filter = ("qtype", "required", "section__survey")
    inlines = [OptionInline]

@admin.register(Interviewer)
class InterviewerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "document_type", "document_number", "phone", "email")
    search_fields = ("full_name", "document_number", "email")

class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ('question', 'text_answer', 'integer_answer', 'decimal_answer', 'bool_answer', 'date_answer', 'options_display')
    fields = ('question', 'text_answer', 'integer_answer', 'decimal_answer', 'bool_answer', 'date_answer', 'options_display')
    can_delete = False

    def options_display(self, obj):
        return ", ".join([option.label for option in obj.options.all()])
    options_display.short_description = "Opciones Seleccionadas"

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
