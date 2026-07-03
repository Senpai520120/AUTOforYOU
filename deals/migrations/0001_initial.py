import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('local_listings', '0005_locallisting_has_contact_in_text'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0007_customuser_is_banned_is_email_verified'),
    ]

    operations = [
        migrations.CreateModel(
            name='Deal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[
                        ('proposed', 'Запропоновано'),
                        ('confirmed', 'Підтверджено'),
                        ('cancelled', 'Скасовано'),
                    ],
                    default='proposed',
                    max_length=20,
                    verbose_name='Статус',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('confirmed_at', models.DateTimeField(blank=True, null=True, verbose_name='Підтверджено о')),
                ('listing', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='deals',
                    to='local_listings.locallisting',
                    verbose_name='Оголошення',
                )),
                ('seller', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='deals_as_seller',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Продавець',
                )),
                ('buyer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='deals_as_buyer',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Покупець',
                )),
            ],
            options={
                'verbose_name': 'Угода',
                'verbose_name_plural': 'Угоди',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveSmallIntegerField(
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(5),
                    ],
                    verbose_name='Оцінка (1-5)',
                )),
                ('text', models.TextField(blank=True, verbose_name='Відгук')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('deal', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='review',
                    to='deals.deal',
                    verbose_name='Угода',
                )),
                ('author', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reviews_written',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Автор',
                )),
                ('target', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reviews_received',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Про кого',
                )),
            ],
            options={
                'verbose_name': 'Відгук',
                'verbose_name_plural': 'Відгуки',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='deal',
            constraint=models.UniqueConstraint(
                fields=['listing', 'buyer'],
                name='unique_deal_listing_buyer',
            ),
        ),
    ]
