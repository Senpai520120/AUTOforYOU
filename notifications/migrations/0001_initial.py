from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(
                    choices=[
                        ('new_message', 'Нове повідомлення'),
                        ('listing_approved', 'Оголошення опубліковано'),
                        ('listing_rejected', 'Оголошення відхилено'),
                        ('listing_expiring', 'Оголошення скоро закінчується'),
                        ('saved_search_match', 'Нове авто за збереженим пошуком'),
                    ],
                    db_index=True,
                    max_length=30,
                )),
                ('title', models.CharField(max_length=255)),
                ('text', models.TextField(blank=True)),
                ('link', models.CharField(blank=True, max_length=500)),
                ('is_read', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notifications',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
