# Задача SSO-1: вход через Keycloak (SSO) с учётками Active Directory, один человек = один email

> Модель сессии: **Opus** (авторизация, чужие токены, привязка учёток). Security-reviewer (Opus) обязателен (`CLAUDE.md`: правки прав доступа и личных данных); замечания «критично» и «важно» исправить до закрытия. Оценка: 1–2 сессии.
> Владелец решил: Keycloak отвечает «кто ты», а **роли, бан и удаление остаются в AUTOforYOU**. Пользователь в Keycloak уникален по email, и в AUTOforYOU он находится по тому же email.

## Конечный результат
Человек с одним email, например `ad_alice@corp.example.test` из Active Directory, нажимает на `/login` кнопку «Увійти через SSO», вводит логин и пароль из AD на странице Keycloak и возвращается на сайт уже вошедшим в **свой** аккаунт AUTOforYOU с этим email. Если он уже вошёл через Keycloak в другое приложение realm (Users & Roles на http://127.0.0.1:8000), форма Keycloak не показывается. Обычный вход по паролю работает как раньше.

## Контекст: что уже готово (в другом репозитории, ничего там не менять)
Keycloak и AD поднимаются из `D:\Django-application-e2e`, ветка `feature/active-directory`:
```powershell
cd D:\Django-application-e2e
docker compose -f docker-compose.yml -f docker-compose.sso.yml -f docker-compose.ad.yml up -d --build --wait
```
- Realm `myapp`. Keycloak для браузера: `http://localhost:8080`, из Docker: `http://keycloak:8080`. Консоль: `http://localhost:8080/admin`, `admin` / `admin`.
- **Issuer в токенах всегда `http://localhost:8080/realms/myapp`** (стоит `KC_HOSTNAME`), даже если запрос шёл на `keycloak:8080`. Discovery: `http://keycloak:8080/realms/myapp/.well-known/openid-configuration`. Авторизация и logout идут на `localhost:8080` (это видит браузер), token и certs на `keycloak:8080`. Проверено: контейнер в сети `sso-shared` получает discovery.
- Client уже заведён: `autoforyou`, confidential, secret `dev-only-autoforyou-secret` (только для dev), PKCE S256 обязателен, direct grants выключены. Redirect URI: `http://localhost/api/v1/auth/oidc/callback/` и `http://localhost:8000/api/v1/auth/oidc/callback/`. Post-logout: `http://localhost/*`, `http://localhost:3000/*`. Чужой redirect Keycloak отклоняет (проверено: 400).
- Сеть Docker `sso-shared` (не external, её создаёт стек Users & Roles; Keycloak в ней доступен как `keycloak`). Стек Users & Roles должен быть запущен **раньше** стека AUTOforYOU.
- В realm `duplicateEmailsAllowed: false` и вход по email разрешён. Люди из AD приходят с `email_verified: true` (`trustEmail`). AD только для чтения: пароли и выключение учёток меняются в AD.
- Тестовые учётки, пароль у всех `demo-password-123`: из AD `ad_alice` (`ad_alice@corp.example.test`), `ad_bob` (`ad_bob@corp.example.test`) и выключенный `ad_disabled`; собственные учётки Keycloak `demo_user` (`demo_user@example.com`) и `demo_admin` (`demo_admin@example.com`).
- Образец той же логики на Django: `D:\Django-application-e2e\accounts\oidc.py` (`filter_users_by_claims`, `verified_email`). Читать для сверки, не копировать: там session-auth через mozilla-django-oidc, а здесь JWT.

## Контекст: AUTOforYOU
- `users.CustomUser`: `USERNAME_FIELD = 'email'`, email уникален. Есть `role`, `is_banned`, `deleted_at`, `deletion_scheduled_at`, `session_version`, `is_email_verified`, `agreed_to_terms_at`.
- Вход: JWT в httpOnly-cookie. Выдача: `users/jwt.py: VersionedRefreshToken.for_user(user)`, cookie ставит `users/cookies.py: set_auth_cookies(response, access, refresh)`, снимает `clear_auth_cookies`. Сессий Django для API нет.
- `users/urls.py` подключён на `/api/v1/auth/`. Там уже есть `AuthConfigView` (`config/`): через него фронт узнаёт, включён ли SSO.
- Фронт: Next.js, страница `frontend/app/login/page.tsx`; сайт за nginx на `http://localhost` (`/api/` проксируется на backend).
- Тесты не ходят в сеть (`core/test_runner.py`), фабрики лежат в `tests/factories.py`.
- **Ловушка cookie:** cookie не различают порты. Users & Roles на `localhost:8000` и AUTOforYOU на `localhost` делят `csrftoken`. В ручной проверке Users & Roles открывать на `http://127.0.0.1:8000`.
- Перед началом: на момент написания `autoforyou-backend-1` был в состоянии `Restarting`. Посмотри `docker compose logs backend` и почини или опиши причину до проверки SSO (это вне задачи, но без живого backend проверка невозможна).

## Решения (не пересматривать без владельца)
1. **Без новой библиотеки OIDC.** Хватит двух view на `requests` и PyJWT: PyJWT уже стоит вместе с SimpleJWT, в нём есть `PyJWKClient`. mozilla-django-oidc не подходит: он логинит в сессию Django, а здесь JWT-cookie.
2. **Привязка:** сначала по `sub` (новая модель `OidcIdentity(user OneToOne, sub unique)`), затем по email, но **только при `email_verified is True`** (`iexact`, ровно один пользователь).
3. **Привилегированные не привязываются автоматически:** `is_staff`, `is_superuser`, `role` в (`broker`, `moderator`, `admin`). Для них management-команда `link_oidc_user <email>=<sub>` с `--replace`. Иначе любая учётка Keycloak с адресом админа получала бы его права.
4. **Новых пользователей SSO не создаёт** (`OIDC_CREATE_USERS=False` по умолчанию). Нет аккаунта с этим email: редирект на `/login?sso_error=no_account` с текстом «Спочатку зареєструйтеся з цим email». Причина: при регистрации пишутся согласия (`users/consents.py`, `agreed_to_terms_at`), обходить их нельзя. Автосоздание с экраном согласия — отдельная задача.
5. **Не пускать:** `is_active=False`, `is_banned`, `deleted_at` или `deletion_scheduled_at` не пустые. Причина в лог, пользователю общий текст.
6. Вход через SSO **не меняет** `role` и группы. `is_email_verified` можно выставить в `True`: адрес подтвердил Keycloak.
7. Флаг `OIDC_ENABLED` (по умолчанию `False`): без него маршрутов нет, кнопки нет, поведение прежнее.

## Шаги
1. **Ветка.** `git switch -c feat/sso-keycloak` от ветки, в которой идёт разработка (сейчас `finish-site`, `main` отстаёт; если неясно, это единственный вопрос владельцу). Чужие незакоммиченные файлы (`.entire/`) не трогать.
2. **Настройки** (`core/settings.py`, обнулить в блоке `if _TESTING:`): `OIDC_ENABLED`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_ISSUER` (= браузерный realm URL, с ним сверяется `iss`), `OIDC_BROWSER_URL`, `OIDC_BACKEND_URL` (по умолчанию = browser), `OIDC_REDIRECT_URI`, `OIDC_POST_LOGOUT_REDIRECT_URI`, `OIDC_CREATE_USERS`. Эндпоинты собрать из двух базовых URL: `/protocol/openid-connect/auth|logout` от browser, `/token|certs` от backend. Discovery не нужен. Все переменные внести в `.env.example`, `.env.docker.example`, `.env.e2e.example` (у вас тест полноты шаблонов `core/tests_env_templates.py`).
3. **Модель** `users.OidcIdentity` и миграция.
4. **`users/oidc.py`** (сервисный слой, без HTTP-view):
   - `build_auth_request(next_path)` возвращает URL Keycloak и данные для cookie: `state`, `nonce`, `code_verifier` (по 32 байта `secrets.token_urlsafe`), `code_challenge` = base64url(SHA256), без `=`. Scope `openid email profile`.
   - `exchange_code(code, code_verifier)`: POST на token endpoint (`grant_type=authorization_code`, `redirect_uri`, `client_id`, `client_secret`, `code_verifier`), таймаут 5 с.
   - `verify_id_token(id_token, nonce)`: `jwt.decode` с ключом из `PyJWKClient(certs_url)` (закешировать на процесс), `algorithms=['RS256']`, `audience=OIDC_CLIENT_ID`, `issuer=OIDC_ISSUER`, обязательные `exp`, `iat`, `sub`; `nonce` совпадает. Ошибка → `OidcError`.
   - `find_user(claims)`: правила 2–5. Гонку двух первых входов закрыть `transaction.atomic` + `IntegrityError` → отказ, как в образце.
5. **View** (`users/views.py` или `users/oidc_views.py`, маршруты `oidc/start/`, `oidc/callback/`, `oidc/logout/` в `users/urls.py` только при `OIDC_ENABLED`):
   - `start` (GET, `AllowAny`): `next` только относительный путь своего сайта (`url_has_allowed_host_and_scheme`, иначе `/`). `state`, `nonce`, `code_verifier` и `next` положить в подписанную httpOnly-cookie `afy_oidc` (`django.core.signing.dumps`, отдельный salt, `max_age` 600, `path=/api/v1/auth/oidc/`, `SameSite=Lax`, `Secure` как у auth-cookie). Ответ 302 на Keycloak.
   - `callback` (GET, `AllowAny`, троттлинг scope `login`): прочитать cookie (`signing.loads`, `max_age`), сверить `state` через `hmac.compare_digest`, пришёл `error` от Keycloak → отказ; обменять code, проверить id_token, `find_user`. Успех: `refresh = VersionedRefreshToken.for_user(user)`, `set_auth_cookies(response, refresh.access_token, refresh)`, удалить `afy_oidc`, обновить `last_login`, 302 на `next`. Любой отказ: удалить `afy_oidc`, 302 на `/login?sso_error=<код>` без подробностей. Токены Keycloak нигде не хранить и не логировать.
   - `logout` (GET): `clear_auth_cookies` + 302 на logout Keycloak с `client_id` и `post_logout_redirect_uri`, чтобы закончилась и сессия Keycloak (single logout). `id_token_hint` не обязателен, Keycloak тогда спросит подтверждение. Это нормально.
   - `AuthConfigView`: добавить `oidc_enabled` (bool) и `oidc_start_url`.
6. **nginx:** `oidc/callback/` и `oidc/start/` добавить в location с лимитом для `token|register` (`nginx/templates`), иначе они уйдут в общий `/api/`.
7. **Команда** `users/management/commands/link_oidc_user.py` (`email=sub`, `--replace`), для привилегированных.
8. **Фронт** (`frontend/app/login/page.tsx`): кнопка «Увійти через SSO» видна, только если `config.oidc_enabled`. Это обычная ссылка `<a href="/api/v1/auth/oidc/start/?next=...">`, не fetch. Показать текст по `sso_error`. В меню выхода: если включён SSO, после обычного logout вести на `/api/v1/auth/oidc/logout/` (или отдельный пункт «Вийти з SSO»; выбрать проще).
9. **Docker:** новый overlay `docker-compose.sso.yml` в AUTOforYOU: `backend` подключён к external-сети `sso-shared` (и к своей default), env `OIDC_*` для dev: `OIDC_BROWSER_URL=http://localhost:8080/realms/myapp`, `OIDC_BACKEND_URL=http://keycloak:8080/realms/myapp`, `OIDC_ISSUER=http://localhost:8080/realms/myapp`, `OIDC_REDIRECT_URI=http://localhost/api/v1/auth/oidc/callback/`, `OIDC_CLIENT_ID=autoforyou`, секрет в `.env`, не в yml. Основной `docker-compose.yml` не менять.
10. **Документация:** раздел «Вхід через SSO (Keycloak + AD)» в README (как запустить оба стека, учётки, правила привязки, ловушка cookie), строка в `CLAUDE.md` и запись в PROGRESS.md.

## Тесты
Django (`users/tests_oidc.py`). Сети нет: RSA-ключ генерировать в тесте, id_token подписывать PyJWT, `requests.post` на token endpoint и `PyJWKClient` мокать. По одному ожидаемому коду в ассерте; каждый тест проверить мутацией.
- `start`: 302 на `localhost:8080/.../auth`, в URL `code_challenge_method=S256` и `client_id=autoforyou`; cookie `afy_oidc` httpOnly; `next=https://evil.example` превращается в `/`.
- `callback` по verified email: существующий пользователь `ad_alice@corp.example.test` получает access/refresh cookie и 302 на `next`; создан `OidcIdentity` с `sub`; повторный вход находит по `sub` и после смены email в Keycloak.
- `email_verified` false или нет → отказ, связь не создана.
- Нет пользователя с таким email → `sso_error=no_account`, пользователь не создан (при `OIDC_CREATE_USERS=False`).
- Привилегированный (staff, superuser, broker, moderator, admin) по email не привязывается; после `link_oidc_user` входит.
- `is_banned`, `is_active=False`, `deleted_at`, `deletion_scheduled_at` → отказ.
- `sub` уже привязан к другому пользователю → отказ; пользователь уже привязан к другому `sub` → отказ.
- Подделки → отказ, cookie не выставлены: `state` не совпал; нет cookie; cookie старше 600 с; чужой `aud`; чужой `iss`; истёкший `exp`; `nonce` не совпал; токен подписан другим ключом; `alg=none`/HS256.
- `error=access_denied` от Keycloak → отказ без обращения к token endpoint.
- Роль и `session_version` после входа не меняются; выданный refresh содержит `sv`.
- `OIDC_ENABLED=False`: маршруты отдают 404, `config` возвращает `oidc_enabled: false`.
- 401 и 403 по правилам брифа к новым эндпоинтам не применимы (они публичные), но покажи в тесте, что callback без cookie ничего не выдаёт.

E2E (Playwright, `frontend/e2e`): один сценарий `@sso` (и `test.skip`, если `E2E_SSO` не задан): `/login` → «Увійти через SSO» → форма Keycloak `ad_alice` / `demo-password-123` → сайт, вошёл под `ad_alice@corp.example.test`. Пользователя создать в `e2e_seed` или фикстурой (правило `@e2e.test` к нему не подходит: email обязан совпасть с AD, указать это в комментарии).

## Проверка руками (критерий «готово»)
1. Поднят стек Users & Roles в режиме AD (команда выше), затем AUTOforYOU: `docker compose -f docker-compose.yml -f docker-compose.sso.yml up -d --build`. Backend healthy.
2. В AUTOforYOU есть обычный пользователь `ad_alice@corp.example.test` с ролью `buyer` (регистрация или shell).
3. `http://localhost/login` → «Увійти через SSO» → Keycloak → `ad_alice` / `demo-password-123` → на сайте вошёл как `ad_alice@corp.example.test`, `/me` открывается, роль прежняя.
4. Единый вход: в новом окне войти в `http://127.0.0.1:8000` как `ad_bob`; затем в AUTOforYOU (с пользователем `ad_bob@corp.example.test`) нажать SSO: форма не показывается.
5. `ad_disabled` и неверный пароль не пускают; email без аккаунта в AUTOforYOU даёт понятный текст `no_account`.
6. Вход по email на форме Keycloak (`ad_alice@corp.example.test` вместо `ad_alice`) тоже работает.
7. Обычный вход по паролю, refresh и logout-all работают как раньше; полный прогон backend-тестов зелёный (через test-runner).

## Файлы
Изменить: `core/settings.py`, `users/urls.py`, `users/views.py` (`AuthConfigView`), `users/models.py`, `nginx/templates/*`, `frontend/app/login/page.tsx` (и место выхода), шаблоны `.env*`, `README.md`, `CLAUDE.md`.
Создать: `users/oidc.py`, `users/migrations/00xx_oidcidentity.py`, `users/management/commands/link_oidc_user.py`, `users/tests_oidc.py`, `docker-compose.sso.yml`, e2e-сценарий.
Не трогать: `D:\Django-application-e2e` (там всё готово), `cars/`, логику обычного входа, блокировки и капчи (1.5), `frontend/e2e/test-1.spec.ts`.
