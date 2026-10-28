/**
 * Серверні адреси (задача 7.3). `server-only`: імпорт з клієнтського компонента ламає збірку,
 * тож внутрішня адреса бекенду (http://backend:8000) не потрапить у бандл браузера.
 */
import 'server-only';
import { API_URL } from './config';

/** Адреса API для рендеру на сервері (у Docker — http://backend:8000), інакше та сама, що й для браузера. */
export const INTERNAL_API_URL = (process.env.INTERNAL_API_URL ?? '').trim().replace(/\/+$/, '') || API_URL;
