import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('local_listings', '0005_locallisting_has_contact_in_text'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0007_customuser_is_banned_is_email_verified'),
    ]

    operations = [
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.CharField(
                    choices=[
                        ('spam', 'Спам або реклама'),
                        ('wrong_info', 'Недостовірна інформація'),
                        ('inappropriate', 'Неприпустимий контент'),
                        ('fraud', 'Шахрайство'),
                        ('duplicate', 'Дублікат оголошення'),
                        ('other', 'Інше'),
                    ],
                    max_length=20,
                    verbose_name='Причина',
                )),
                ('comment', models.TextField(blank=True, verbose_name='Коментар')),
                ('status', models.CharField(
                    choices=[
                        ('new', 'Нова'),
                        ('reviewed', 'Розглянута'),
                        ('dismissed', 'Відхилена'),
                    ],
                    default='new',
                    max_length=20,
                    verbose_name='Статус',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reporter', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reports_sent',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Скаржник',
                )),
                ('listing', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reports',
                    to='local_listings.locallisting',
                    verbose_name='Оголошення',
                )),
                ('reported_user', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='reports_received',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Скаржимося на користувача',
                )),
            ],
            options={
                'verbose_name': 'Скарга',
                'verbose_name_plural': 'Скарги',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='report',
            constraint=models.UniqueConstraint(
                condition=Q(listing__isnull=False, status='new'),
                fields=['reporter', 'listing'],
                name='unique_active_report_listing',
            ),
        ),
        migrations.AddConstraint(
            model_name='report',
            constraint=models.UniqueConstraint(
                condition=Q(reported_user__isnull=False, status='new'),
                fields=['reporter', 'reported_user'],
                name='unique_active_report_user',
            ),
        ),
    ]
