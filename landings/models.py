from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from content.models import DRAFT_MARKER_ERROR, _PublishableText, has_draft_marker
from pricing.models import AuctionFeeTier

SLUG_VALIDATOR = RegexValidator(
    r'^[a-z0-9]+(?:-[a-z0-9]+)*$', 'Лише малі латинські літери, цифри та дефіс.')
NO_CALCULATION_ERROR = (
    'Не можна опублікувати без розрахунку: заповніть вхідні дані та переконайтеся, що діють усі ставки.')

THIN_TEXT_ERROR = ('Текст замалий: {length} із {minimum} символів (вступ, опис, що входить у ціну). '
                   'Допишіть унікальний текст про модель.')


class LandingFuel(models.TextChoices):
    PETROL = 'petrol', 'Бензин'
    DIESEL = 'diesel', 'Дизель'
    ELECTRIC = 'electric', 'Електро'
    HYBRID = 'hybrid', 'Гібрид'
    PHEV = 'phev', 'Гібрид (PHEV)'


EV_FUELS = (LandingFuel.ELECTRIC, LandingFuel.PHEV)


class ModelLandingPage(models.Model):
    """SEO-сторінка «Пригон [модель] з США». Вхідні дані розрахунку та тексти веде власник в адмінці."""

    slug = models.CharField('Slug', max_length=100, unique=True, validators=[SLUG_VALIDATOR],
                            help_text='Латиницею, адреса: /prigon/<slug>. Після публікації не змінюйте.')
    make = models.CharField('Марка', max_length=60)
    model = models.CharField('Модель', max_length=80)
    year_from = models.PositiveSmallIntegerField('Роки випуску: від', null=True, blank=True,
                                                 validators=[MinValueValidator(1900), MaxValueValidator(2100)])
    year_to = models.PositiveSmallIntegerField('Роки випуску: до', null=True, blank=True,
                                               validators=[MinValueValidator(1900), MaxValueValidator(2100)])

    # Типові входи розрахунку (ті самі поля й довідники, що у калькулятора).
    calc_year = models.PositiveSmallIntegerField(
        'Рік авто для розрахунку', null=True, blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(2100)],
        help_text='Від нього залежить акциз (вік авто). Має лежати між «від» і «до».')
    auction_price_usd = models.DecimalField(
        'Типова ціна на аукціоні, USD', max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)], help_text='Вносить власник; без неї сторінку не опублікувати.')
    fuel_type = models.CharField('Паливо', max_length=10, choices=LandingFuel.choices, blank=True)
    engine_cc = models.PositiveIntegerField('Об’єм двигуна, см³', null=True, blank=True,
                                            validators=[MaxValueValidator(10000)])
    battery_capacity_kwh = models.DecimalField(
        'Ємність батареї, кВт·год', max_digits=5, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(300)], help_text='Лише для електро та PHEV.')
    generation = models.CharField('Покоління / кузов', max_length=100, blank=True,
                                  help_text='Вільний текст, наприклад «XV70». Порожньо - не показується.')
    auction = models.CharField('Аукціон', max_length=10, choices=AuctionFeeTier.Auction.choices,
                               default=AuctionFeeTier.Auction.COPART)
    auction_location = models.CharField('Локація майданчика', max_length=100, blank=True)
    us_port = models.CharField('Порт США', max_length=50, blank=True)
    eu_port = models.CharField('Порт ЄС', max_length=20, blank=True)

    # Тексти.
    h1 = models.CharField('Заголовок H1', max_length=200, blank=True,
                          help_text='Порожньо - «Пригон <марка модель> з США - ціна під ключ».')
    intro = models.TextField('Вступ', blank=True)
    description = models.TextField('Опис', blank=True)
    included_text = models.TextField('Що входить у ціну', blank=True)
    typical_term_text = models.CharField(
        'Орієнтовний термін', max_length=200, blank=True,
        help_text='Вільний текст, який вносить власник; не обчислюється.')
    meta_title = models.CharField('Meta title', max_length=120, blank=True)
    meta_description = models.CharField('Meta description', max_length=300, blank=True)

    is_published = models.BooleanField('Опубліковано', default=False)
    sort_order = models.PositiveIntegerField('Порядок', default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'make', 'model', 'id']
        verbose_name = 'Сторінка моделі'
        verbose_name_plural = 'Сторінки моделей'

    TEXT_FIELDS = ('h1', 'intro', 'description', 'included_text', 'typical_term_text',
                   'meta_title', 'meta_description')

    def __str__(self):
        return f'{self.make} {self.model}'.strip()

    @property
    def title(self) -> str:
        return f'{self.make} {self.model}'.strip()

    def has_draft_marker(self) -> bool:
        return has_draft_marker(*(getattr(self, f) for f in self.TEXT_FIELDS))

    def _was_published(self) -> bool:
        return bool(self.pk) and ModelLandingPage.objects.filter(pk=self.pk, is_published=True).exists()

    def publication_error(self, *, check_text: bool = True) -> str | None:
        """Единственное место условий публикации: позначка, расчёт, порог текста (его - только при переходе)."""
        from .services import can_publish, text_length_error
        if self.has_draft_marker():
            return DRAFT_MARKER_ERROR
        if not can_publish(self):
            return NO_CALCULATION_ERROR
        return text_length_error(self) if check_text else None

    def clean(self):
        super().clean()
        errors = {}
        if self.year_from and self.year_to and self.year_from > self.year_to:
            errors['year_to'] = 'Рік «до» не може бути меншим за «від».'
        if self.calc_year:
            if (self.year_from and self.calc_year < self.year_from) or (self.year_to and self.calc_year > self.year_to):
                errors['calc_year'] = 'Рік для розрахунку поза діапазоном років випуску.'
        if self.is_published:
            error = self.publication_error(check_text=not self._was_published())
            if error:
                errors['is_published'] = error
        if errors:
            raise ValidationError(errors)


class LandingSettings(models.Model):
    """Singleton (pk=1): рекомендована межа опублікованих сторінок. Підняти до 50 - правка поля."""

    max_published = models.PositiveSmallIntegerField(
        'Рекомендована максимальна кількість опублікованих сторінок', default=30,
        validators=[MinValueValidator(1)],
        help_text='Перевищення не блокує публікацію, лише показує попередження в адмінці.')
    min_text_chars = models.PositiveSmallIntegerField(
        'Мінімальна довжина унікального тексту', default=600, validators=[MinValueValidator(100)],
        help_text='Сума символів «Вступ» + «Опис» + «Що входить у ціну». Перевіряється лише при публікації; '
                  'уже опубліковані сторінки не знімаються.')

    class Meta:
        verbose_name = 'Налаштування сторінок моделей'
        verbose_name_plural = 'Налаштування сторінок моделей'

    def __str__(self):
        return 'Налаштування сторінок моделей'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        return cls.objects.get_or_create(pk=1)[0]


class LandingFaqItem(_PublishableText):
    """Питання-відповідь про конкретну модель. Показується на сторінці, лише якщо активне й без чернеткової позначки."""

    text_fields = ('question', 'answer')

    page = models.ForeignKey(ModelLandingPage, on_delete=models.CASCADE, related_name='faq_items',
                             verbose_name='Сторінка моделі')
    question = models.CharField('Питання', max_length=300)
    answer = models.TextField('Відповідь', help_text='Звичайний текст; HTML не підтримується.')

    class Meta(_PublishableText.Meta):
        verbose_name = 'Питання про модель'
        verbose_name_plural = 'Питання про модель'

    def __str__(self):
        return self.question
