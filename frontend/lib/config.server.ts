/**
 * Серверні адреси (задача 7.3). `server-only`: імпорт з клієнтського компонента ламає збірку,
 * тож внутрішня адреса бекенду (http://backend:8000) не потрапить у бандл браузера.
 */
import 'server-only';
import { API_URL } from './config';

/** Адреса API для рендеру на сервері (у Docker — http://backend:8000), інакше та сама, що й для браузера. */
/**
 * Спільний секрет SSR ↔ backend (задача 12.4). Тільки сервер: без NEXT_PUBLIC, не потрапляє в бандл.
 * Порожній або коротший за 32 символи — функція вимкнена (backend теж її ігнорує).
 */
export const SSR_INTERNAL_KEY = (process.env.SSR_INTERNAL_KEY ?? '').trim();

export const INTERNAL_API_URL = (process.env.INTERNAL_API_URL ?? '').trim().replace(/\/+$/, '') || API_URL;
