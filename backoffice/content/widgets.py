import json
from django import forms
from django.utils.html import format_html

class ConstructorWidget(forms.Textarea):
    template_name = 'content/widget.html'

    def __init__(self, schema=None, attrs=None):
        super().__init__(attrs)
        self.schema = schema or {'type': 'object', 'properties': {}}

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['attrs']['data-schema'] = json.dumps(self.schema, ensure_ascii=False)
        return context

    class Media:
        js = ('content/constructor.js',)
        css = {'all': ('content/constructor.css',)}
