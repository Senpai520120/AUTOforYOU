from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_customuser_agreed_to_terms_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='is_banned',
            field=models.BooleanField(default=False, verbose_name='Забанений'),
        ),
        migrations.AddField(
            model_name='customuser',
            name='is_email_verified',
            field=models.BooleanField(default=False, verbose_name='Email підтверджено'),
        ),
    ]
