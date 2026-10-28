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

/**
 * Мітка «вхід через SSO» (задача SSO-1): `afy_sso=1`, ставить callback Keycloak
 * (AUTH_COOKIE_SSO_HINT_NAME). Після виходу такого користувача ведемо на logout Keycloak,
 * інакше SSO одразу впустить його знову.
 */
export function hasSsoHint(): boolean {
  return readCookie('afy_sso') === '1';
}
