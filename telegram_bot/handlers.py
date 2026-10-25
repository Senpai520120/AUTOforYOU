import logging
import uuid

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from telegram_bot.formatting import listing_card_html
from telegram_bot.texts import aget_text

logger = logging.getLogger(__name__)
router = Router(name='autoforyou')


# ─── /start ──────────────────────────────────────────────────────────────────

@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(message: Message, command: CommandObject) -> None:
    payload = command.args or ''
    if payload.startswith('link_'):
        await _handle_link_token(message, payload[5:])
    else:
        await message.answer(await aget_text('start_other_payload'), parse_mode='HTML')


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(await aget_text('start'), parse_mode='HTML')


# ─── /help ───────────────────────────────────────────────────────────────────

@router.message(Command('help'))
async def cmd_help(message: Message) -> None:
    await message.answer(await aget_text('help'), parse_mode='HTML')


# ─── /unlink ─────────────────────────────────────────────────────────────────

@router.message(Command('unlink'))
async def cmd_unlink(message: Message) -> None:
    from asgiref.sync import sync_to_async

    from telegram_bot.models import unlink_telegram
    from users.models import CustomUser

    @sync_to_async
    def _unlink(telegram_id: int) -> bool:
        user_id = CustomUser.objects.filter(telegram_id=telegram_id).values_list('pk', flat=True).first()
        return user_id is not None and unlink_telegram(user_id)

    unlinked = await _unlink(message.from_user.id)
    await message.answer(await aget_text('unlink_ok' if unlinked else 'unlink_not_linked'), parse_mode='HTML')


# ─── /latest ─────────────────────────────────────────────────────────────────

@router.message(Command('latest'))
async def cmd_latest(message: Message) -> None:
    from asgiref.sync import sync_to_async
    from django.conf import settings

    from core.modules import module_enabled

    @sync_to_async
    def _fetch():
        if not module_enabled('lots'):
            return []
        from listings.models import Listing
        qs = (
            Listing.objects
            .filter(status__in=['in_stock', 'in_transit'], channel='retail')
            .select_related('vehicle')
            .prefetch_related('vehicle__images')
            .order_by('-created_at')[:5]
        )
        result = []
        for listing in qs:
            v = listing.vehicle
            img = (
                v.images.filter(is_primary=True).first()
                or v.images.first()
            )
            result.append({
                'id': listing.pk,
                'title_parts': (v.make, v.model, v.year),
                'price': listing.price,
                'currency': listing.currency,
                'status': listing.get_status_display(),
                'photo_url': (img.source_url or '') if img else '',
            })
        return result

    items = await _fetch()
    if not items:
        await message.answer(await aget_text('latest_empty'), parse_mode='HTML')
        return

    site_url = getattr(settings, 'SITE_URL', 'https://autoforyou.ua')
    button_text = await aget_text('btn_view')
    for item in items:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=button_text,
                url=f'{site_url}/listings/{item["id"]}',
            )
        ]])
        # Шаблон читается из БД/кэша: вне async-потока ORM недоступен.
        text = await sync_to_async(listing_card_html)(
            item['title_parts'], item['price'], item['currency'], item['status'])
        await message.answer(text, reply_markup=kb, parse_mode='HTML')


# ─── Deep-link: привязка аккаунта ────────────────────────────────────────────

async def _handle_link_token(message: Message, token_str: str) -> None:
    from asgiref.sync import sync_to_async

    @sync_to_async
    def _process(telegram_id: int, token_str: str) -> str:
        from django.db import IntegrityError, transaction

        from telegram_bot.models import TelegramLinkToken
        from users.models import CustomUser

        try:
            token_uuid = uuid.UUID(token_str)
        except ValueError:
            return 'invalid'

        # Проверка и погашение токена атомарны: строка блокируется на время транзакции,
        # из двух параллельных апдейтов с одним токеном второй увидит used=True.
        with transaction.atomic():
            try:
                token_obj = (
                    TelegramLinkToken.objects.select_for_update(of=('self',))
                    .select_related('user').get(token=token_uuid)
                )
            except TelegramLinkToken.DoesNotExist:
                return 'invalid'

            if not token_obj.is_valid():
                return 'expired'

            user = token_obj.user
            if user.telegram_id == telegram_id:
                return 'already'
            if CustomUser.objects.filter(telegram_id=telegram_id).exclude(pk=user.pk).exists():
                return 'taken'

            # Условное погашение: страховка там, где блокировка строк недоступна (SQLite).
            if not TelegramLinkToken.objects.filter(pk=token_obj.pk, used=False).update(used=True):
                return 'expired'
            try:
                with transaction.atomic():  # savepoint: IntegrityError не ломает внешнюю транзакцию
                    user.telegram_id = telegram_id
                    user.save(update_fields=['telegram_id'])
            except IntegrityError:
                transaction.set_rollback(True)  # откатывается и погашение: токен остаётся неиспользованным
                return 'taken'
            return 'ok'

    result = await _process(message.from_user.id, token_str)
    key = {
        'ok': 'link_ok', 'already': 'link_already', 'taken': 'link_taken', 'expired': 'link_expired',
    }.get(result, 'link_invalid')
    await message.answer(await aget_text(key), parse_mode='HTML')
