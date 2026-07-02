from django.db import migrations

# УВАГА: підігнати ціни під реальні перед запуском у продакшені
TARIFFS = [
    # (code, name, type, price, currency, duration_days, description)
    ('renew_30', 'Продовження на 30 днів', 'renew', '49.00', 'UAH', 30,
     'Продовжує термін дії оголошення на 30 днів і повертає його в каталог, якщо воно знято.'),
    ('bump_once', 'Підняти в топ списку', 'bump', '29.00', 'UAH', 0,
     'Одноразово піднімає оголошення вгору списку.'),
    ('top_7', 'ТОП 7 днів', 'top', '99.00', 'UAH', 7,
     'Закріплює оголошення у ТОП-блоці каталогу на 7 днів.'),
    ('top_30', 'ТОП 30 днів', 'top', '299.00', 'UAH', 30,
     'Закріплює оголошення у ТОП-блоці каталогу на 30 днів.'),
]


def seed(apps, schema_editor):
    PromotionTariff = apps.get_model('local_listings', 'PromotionTariff')
    for code, name, ttype, price, currency, days, desc in TARIFFS:
        PromotionTariff.objects.get_or_create(
            code=code,
            defaults=dict(name=name, type=ttype, price=price, currency=currency,
                          duration_days=days, description=desc, active=True),
        )


def unseed(apps, schema_editor):
    apps.get_model('local_listings', 'PromotionTariff').objects.filter(
        code__in=[t[0] for t in TARIFFS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('local_listings', '0003_lifecycle_and_promotion'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
