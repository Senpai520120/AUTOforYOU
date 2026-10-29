/**
 * Мітка «є сесія» (задача 1.4): cookie `has_session=1` без токена, не httpOnly.
 * Бекенд ставить її разом з access/refresh і видаляє разом з ними
 * (users/cookies.py, AUTH_COOKIE_HINT_NAME). Без мітки фронт не питає
 * profile і не робить refresh — гість не витрачає анонімний ліміт запитів.
 */
import { readCookie } from './csrf';

export function hasSessionHint(): boolean {
  return readCookie('has_session') === '1';
}
