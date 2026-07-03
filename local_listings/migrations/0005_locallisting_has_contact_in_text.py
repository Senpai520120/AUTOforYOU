from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('local_listings', '0004_seed_promotion_tariffs'),
    ]

    operations = [
        migrations.AddField(
            model_name='locallisting',
            name='has_contact_in_text',
            field=models.BooleanField(db_index=True, default=False, verbose_name='Контакт у тексті (антиспам)'),
        ),
    ]
