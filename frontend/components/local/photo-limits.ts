/**
 * Перевірка фото до відправки за лімітами з GET /api/v1/local/config/ (задача 4.2, 10-S6, 10-C2).
 * Хардкоду кількості й розміру немає: значення задає сервер (.env).
 */
import { LocalConfig } from '@/lib/types';

export interface PhotoCheck {
  accepted: File[];
  error: string;
}

const EXT: Record<string, string> = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' };

export function allowedHuman(config: LocalConfig): string {
  return config.allowed_types.map(t => EXT[t] ?? t.replace('image/', '')).join('/');
}

export function photoHint(config: LocalConfig, count: number): string {
  return `${count}/${config.max_photos} · ${allowedHuman(config)} · до ${config.photo_max_size_mb} МБ`;
}

/** Відбирає придатні файли; невідповідні не відправляються, причина — у `error`. */
export function checkPhotos(files: File[], config: LocalConfig, alreadyCount: number): PhotoCheck {
  const errors: string[] = [];
  const accepted: File[] = [];
  const maxBytes = config.photo_max_size_mb * 1024 * 1024;
  for (const f of files) {
    if (!config.allowed_types.includes(f.type)) {
      errors.push(`«${f.name}»: непідтримуваний формат (лише ${allowedHuman(config)}).`);
    } else if (f.size > maxBytes) {
      errors.push(`«${f.name}»: файл більший за ${config.photo_max_size_mb} МБ.`);
    } else {
      accepted.push(f);
    }
  }
  const room = Math.max(0, config.max_photos - alreadyCount);
  if (accepted.length > room) {
    errors.push(`Можна додати не більше ${config.max_photos} фото.`);
    accepted.splice(room);
  }
  return { accepted, error: errors.join(' ') };
}
