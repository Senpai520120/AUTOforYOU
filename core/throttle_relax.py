"""Один флаг E2E_RELAX_THROTTLES вместо набора THROTTLE_*_RATE в .env.e2e (задача 9.58).

Весь набор Playwright идёт с одного IP, и боевые лимиты (калькулятор 30/час, заявки 5/час, и т.д.) дают 429
посреди прогона. Флаг поднимает лимиты DRF до `RELAXED_RATE`, но только если одновременно задан
`E2E_SEED_ALLOWED=true` (признак тестового стека, тот же, что разрешает `e2e_seed`).

Не затрагивает: блокировку входа по неудачным попыткам (`LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_MINUTES`) и лимит
`client_errors` (его реальный 429 проверяет error-monitoring.spec.ts). `launch_check` на проде ругается ошибкой, если
флаг включён (core/launch.py, check_flags).

Чистые функции без Django: проверяются тестами без перезагрузки settings.
"""
from collections.abc import Mapping

RELAXED_RATE = '100000/hour'
# Лимиты, которые флаг не трогает: на них держатся реальные проверки 429.
KEEP_SCOPES = ('client_errors',)
_TRUE = ('true', '1', 'yes')


def _on(env: Mapping, name: str) -> bool:
    return str(env.get(name, '')).strip().lower() in _TRUE


def _seed_allowed(env: Mapping) -> bool:
    """Строго как в e2e_seed (require_e2e_allowed): только 'true' (регистр и пробелы не важны), без '1' и 'yes'."""
    return str(env.get('E2E_SEED_ALLOWED', '')).strip().lower() == 'true'


def relax_requested(env: Mapping) -> bool:
    """Флаг включён в окружении (даже если он будет проигнорирован). Нужен launch_check."""
    return _on(env, 'E2E_RELAX_THROTTLES')


def relax_rates(rates: Mapping, env: Mapping) -> tuple[dict, bool]:
    """(лимиты, применён ли флаг). Без E2E_SEED_ALLOWED=true лимиты возвращаются боевыми, без изменений."""
    if relax_requested(env) and _seed_allowed(env):
        return {scope: (rate if scope in KEEP_SCOPES else RELAXED_RATE) for scope, rate in rates.items()}, True
    return dict(rates), False
