from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Survey, Section, Question, Option, ResponseSet, Answer, AccessToken

class OptionInline(admin.TabularInline):
    model = Option
    extra = 1

class QuestionAdmin(admin.ModelAdmin):
    list_display = ('section', 'order', 'code', 'qtype', 'required')
    list_filter = ('section__survey', 'qtype', 'required')
    search_fields = ('code', 'text')
    inlines = [OptionInline]
    ordering = ('section__survey', 'section__order', 'order')

class SectionAdmin(admin.ModelAdmin):
    list_display = ('survey', 'order', 'title')
    list_filter = ('survey',)
    ordering = ('survey', 'order')

class ResponseSetAdmin(admin.ModelAdmin):
    list_display = ('survey', 'identificacion', 'created_at', 'zarit_score', 'zarit_category')
    list_filter = ('survey', 'zarit_category', 'created_at')
    search_fields = ('identificacion', 'full_name', 'email', 'phone')
    readonly_fields = ('zarit_score', 'zarit_category')

admin.site.register(Survey)
admin.site.register(Section, SectionAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(ResponseSet, ResponseSetAdmin)
admin.site.register(Answer)
admin.site.register(AccessToken)
