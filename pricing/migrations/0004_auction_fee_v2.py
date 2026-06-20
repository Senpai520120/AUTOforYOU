"""
Миграция: заменяем старую AuctionFeeTier (min_price_usd/fee_pct)
на новую с member_type/payment_type/title_type/fee_flat/fee_percent
и создаём AuctionFixedFee.

Данные старых тиров удаляем — они будут пересозданы командой seed_auction_fees.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0003_excise_rate_real_values'),
    ]

    operations = [
        # 1. Удаляем старую модель AuctionFeeTier целиком
        migrations.DeleteModel(
            name='AuctionFeeTier',
        ),

        # 2. Создаём новую AuctionFeeTier с расширенной сеткой
        migrations.CreateModel(
            name='AuctionFeeTier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valid_from', models.DateField(verbose_name='Действует с')),
                ('valid_to', models.DateField(blank=True, null=True, verbose_name='Действует по')),
                ('auction', models.CharField(
                    choices=[('copart', 'Copart'), ('iaai', 'IAAI')],
                    max_length=10, verbose_name='Аукцион',
                )),
                ('member_type', models.CharField(
                    choices=[('public', 'Публичный'), ('licensed', 'Лицензированный дилер'), ('broker', 'Брокер')],
                    default='public', max_length=10, verbose_name='Тип участника',
                )),
                ('payment_type', models.CharField(
                    choices=[('secured', 'Обеспечённый'), ('unsecured', 'Необеспечённый')],
                    default='secured', max_length=10, verbose_name='Тип оплаты',
                )),
                ('title_type', models.CharField(
                    choices=[('clean', 'Чистый (clean)'), ('salvage', 'Salvage / Rebuildable'), ('any', 'Любой (не различается)')],
                    default='any', max_length=10, verbose_name='Тип титула',
                )),
                ('bid_min', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Ставка от ($)')),
                ('bid_max', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=10, null=True,
                    verbose_name='Ставка до ($, пусто=без лимита)',
                )),
                ('fee_flat', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=8, null=True,
                    verbose_name='Фикс. сбор ($)',
                )),
                ('fee_percent', models.DecimalField(
                    blank=True, decimal_places=4, max_digits=6, null=True,
                    verbose_name='% от ставки (напр. 0.0600 = 6%)',
                )),
            ],
            options={
                'verbose_name': 'Тиер buyer fee',
                'verbose_name_plural': 'Тиеры buyer fee',
                'ordering': ['auction', 'member_type', 'bid_min'],
            },
        ),

        # 3. Создаём AuctionFixedFee
        migrations.CreateModel(
            name='AuctionFixedFee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valid_from', models.DateField(verbose_name='Действует с')),
                ('valid_to', models.DateField(blank=True, null=True, verbose_name='Действует по')),
                ('auction', models.CharField(
                    choices=[('copart', 'Copart'), ('iaai', 'IAAI')],
                    max_length=10, verbose_name='Аукцион',
                )),
                ('fee_type', models.CharField(
                    choices=[('gate', 'Gate / Service fee'), ('environmental', 'Environmental fee'), ('virtual_bid', 'Virtual bid fee')],
                    max_length=20, verbose_name='Тип сбора',
                )),
                ('title_type', models.CharField(
                    choices=[('clean', 'Чистый (clean)'), ('salvage', 'Salvage / Rebuildable'), ('any', 'Любой')],
                    default='any', max_length=10,
                    verbose_name='Тип титула (актуально для gate fee)',
                )),
                ('amount', models.DecimalField(decimal_places=2, max_digits=8, verbose_name='Сумма ($)')),
            ],
            options={
                'verbose_name': 'Фиксированный сбор аукциона',
                'verbose_name_plural': 'Фиксированные сборы аукциона',
                'ordering': ['auction', 'fee_type'],
            },
        ),
    ]
