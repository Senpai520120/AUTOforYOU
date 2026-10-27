from django.core.exceptions import ValidationError
from django.db import models

HOW_IT_WORKS_CACHE_KEY = 'content:how-it-works'
FAQ_CACHE_KEY = 'content:faq:{place}'
FAQ_PLACES = ('calculator',)

# Чернетки з міграції містять позначку «[ПЕРЕВІРИТИ З БРОКЕРОМ: ...]». Вмикати запис з нею не можна,
# щоб чернетка не потрапила на сайт.
DRAFT_MARKER = 'ПЕРЕВІРИТИ'
DRAFT_MARKER_ERROR = 'Приберіть позначку «перевірити з брокером» перед публікацією'


def has_draft_marker(*texts: str) -> bool:
    return any(DRAFT_MARKER in (t or '').upper() for t in texts)


class _PublishableText(models.Model):
    """Запис, який не можна вмикати, поки в тексті лишається чернеткова позначка."""

    text_fields: tuple[str, ...] = ()

    order = models.PositiveIntegerField('Порядок', default=0, db_index=True)
    is_active = models.BooleanField('Активно', default=False)

    class Meta:
        abstract = True
        ordering = ['order', 'id']

    def clean(self):
        super().clean()
        if self.is_active and has_draft_marker(*(getattr(self, f) for f in self.text_fields)):
            raise ValidationError(DRAFT_MARKER_ERROR)


class ImportStep(_PublishableText):
    """Етап пригону для сторінки «Як працює пригон». Усі поля - текст, без чисел із коду."""

    text_fields = ('title', 'description', 'duration')

    title = models.CharField('Заголовок', max_length=200)
    description = models.TextField('Опис', blank=True)
    duration = models.CharField('Термін', max_length=200, blank=True,
                                help_text='Вільний текст, наприклад «2–3 тижні». Порожньо - не показується.')

    class Meta(_PublishableText.Meta):
        verbose_name = 'Етап пригону'
        verbose_name_plural = 'Етапи пригону'

    def __str__(self):
        return self.title


class FaqItem(_PublishableText):
    """Питання-відповідь для /how-it-works і (за прапорцем) для сторінки калькулятора."""

    text_fields = ('question', 'answer')

    question = models.CharField('Питання', max_length=300)
    answer = models.TextField('Відповідь', help_text='Звичайний текст; HTML не підтримується.')
    show_on_calculator = models.BooleanField('Показувати під калькулятором', default=False)

    class Meta(_PublishableText.Meta):
        verbose_name = 'Питання та відповідь'
        verbose_name_plural = 'Питання та відповіді'

    def __str__(self):
        return self.question
