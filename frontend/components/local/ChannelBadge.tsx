// Бейдж «від @канал» (задача 9.57): оголошення внесено вручну з Telegram-каналу за згодою його власника.
// Перевірка імені й побудова посилання - у lib/channel.ts.
import { channelUrl } from '@/lib/channel';

export default function ChannelBadge({ channel, className = '' }: { channel?: string | null; className?: string }) {
  const url = channelUrl(channel);
  if (!url) return null;
  return (
    <a
      href={url}
      target="_blank"
      rel="nofollow noopener noreferrer"
      data-testid="channel-badge"
      className={`inline-block text-xs bg-card text-link border border-border rounded-full px-2 py-0.5 hover:border-primary ${className}`}
    >
      від @{channel}
    </a>
  );
}
