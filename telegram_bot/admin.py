from django import forms
from django.contrib import admin

from .models import BotText, TelegramLinkToken
from .texts import REGISTRY


@admin.register(TelegramLinkToken)
class TelegramLinkTokenAdmin(admin.ModelAdmin):
    """Только просмотр: токен — одноразовый секрет привязки, показываем первые 8 символов."""
    list_display = ['user', 'token_masked', 'expires_at', 'used', 'created_at']
    list_filter = ['used']
    fields = ['user', 'token_masked', 'expires_at', 'used', 'created_at']
    readonly_fields = fields
    search_fields = ['user__email']

    @admin.display(description='Токен')
    def token_masked(self, obj):
        return f'{str(obj.token)[:8]}…'

    def has_add_permission(self, request):
        return False


class BotTextForm(forms.ModelForm):
    class Meta:
        model = BotText
        fields = ['key', 'text']
        widgets = {'text': forms.Textarea(attrs={'rows': 8, 'cols': 90})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'key' not in self.fields:  # при изменении ключ только для чтения
            return
        self.fields['key'] = forms.ChoiceField(
            label='Ключ', choices=[(k, f'{k} — {d.description}') for k, d in REGISTRY.items()],
        )


@admin.register(BotText)
class BotTextAdmin(admin.ModelAdmin):
    form = BotTextForm
    list_display = ['key', 'description', 'short_text', 'updated_at']
    search_fields = ['key', 'text']
    readonly_fields = ['description', 'allowed_placeholders', 'updated_at']

    def get_fields(self, request, obj=None):
        if obj:
            return ['key', 'description', 'allowed_placeholders', 'text', 'updated_at']
        return ['key', 'text']

    def get_readonly_fields(self, request, obj=None):
        base = list(super().get_readonly_fields(request, obj))
        return base + ['key'] if obj else base

    @admin.display(description='Описание')
    def description(self, obj):
        definition = REGISTRY.get(obj.key)
        return definition.description if definition else '— (ключа нет в реестре)'

    @admin.display(description='Допустимые плейсхолдеры')
    def allowed_placeholders(self, obj):
        definition = REGISTRY.get(obj.key)
        if not definition or not definition.placeholders:
            return 'нет'
        kind = 'HTML: теги b, i, u, s, a, code, pre' if definition.kind == 'html' else 'обычный текст, без тегов'
        return ', '.join('{%s}' % p for p in definition.placeholders) + f' ({kind})'

    @admin.display(description='Текст')
    def short_text(self, obj):
        return obj.text[:80]
