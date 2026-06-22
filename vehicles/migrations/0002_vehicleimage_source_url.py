from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicleimage',
            name='source_url',
            field=models.CharField(blank=True, max_length=500, verbose_name='URL источника фото'),
        ),
        migrations.AlterField(
            model_name='vehicleimage',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='vehicle_photos/'),
        ),
    ]
