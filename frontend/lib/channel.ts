// Ім'я Telegram-каналу для бейджа «від @канал» (задача 9.57). Чисті функції без імпортів: перевіряються без браузера.
// Формат дзеркалить бекенд (local_listings.models.TELEGRAM_CHANNEL_RE): латиниця, цифри, _, 5-32 символи, перша - буква.
const CHANNEL_RE = /^[A-Za-z][A-Za-z0-9_]{4,31}$/;

export function isChannelName(channel: string | null | undefined): channel is string {
  return typeof channel === 'string' && CHANNEL_RE.test(channel);
}

/** Посилання збирається лише з перевіреного імені на фіксований хост: javascript: і чужі домени неможливі. */
export function channelUrl(channel: string | null | undefined): string | null {
  return isChannelName(channel) ? `https://t.me/${channel}` : null;
}
