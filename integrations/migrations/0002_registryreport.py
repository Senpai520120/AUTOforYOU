from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegistryReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vin', models.CharField(blank=True, max_length=17, null=True, verbose_name='VIN')),
                ('plate', models.CharField(blank=True, max_length=20, null=True, verbose_name='Госномер')),
                ('provider', models.CharField(max_length=50, verbose_name='Провайдер')),
                ('payload', models.JSONField(verbose_name='Данные отчёта')),
                ('demo', models.BooleanField(default=False, verbose_name='Демо-данные')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Отчёт реестра UA',
                'verbose_name_plural': 'Отчёты реестра UA',
                'ordering': ['-created_at'],
            },
        ),
    ]
