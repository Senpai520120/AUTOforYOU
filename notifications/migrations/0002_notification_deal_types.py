from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='type',
            field=models.CharField(
                choices=[
                    ('new_message', 'Нове повідомлення'),
                    ('listing_approved', 'Оголошення опубліковано'),
                    ('listing_rejected', 'Оголошення відхилено'),
                    ('listing_expiring', 'Оголошення скоро закінчується'),
                    ('saved_search_match', 'Нове авто за збереженим пошуком'),
                    ('deal_proposed', 'Пропозиція угоди'),
                    ('deal_confirmed', 'Угода підтверджена'),
                    ('deal_cancelled', 'Угода скасована'),
                    ('review_received', 'Новий відгук'),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]
