# AUTOforYOU 🚗

> Маркетплейс автомобілів: імпорт з аукціонів США під ключ і каталог місцевих оголошень по Україні.

---

## Два напрямки

Проєкт складається з двох частин з різною логікою — це видно і в навігації сайту.

| Напрямок | Що це | Розділи |
|---|---|---|
| **Імпорт з США** | Лоти Copart та IAAI, розрахунок вартості «під ключ», відстеження контейнера | `/listings`, `/calculator`, `/b2b`, `/me/shipments` |
| **Каталог Україна** | C2C-оголошення від власників і дилерів з модерацією, повідомленнями, угодами й відгуками | `/ua`, `/local/*`, `/me/*` |

## Стек

| Шар | Технологія |
|-----|-----------|
| Backend | Python 3.12, Django 6, DRF, SimpleJWT |
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind CSS |
| БД | PostgreSQL (SQLite для локальної розробки без налаштування) |
| Черга задач | Celery + Redis, django-celery-beat для розкладу |
| Платежі | LiqPay (протокол v3, власний клієнт) |
| Сповіщення | Telegram-бот на aiogram 3 |
| Розгортання | Docker Compose: nginx, backend, frontend, celery worker і beat, bot, db, redis |
| API-документація | drf-spectacular (Swagger / ReDoc) |
| Тести | Django test runner (417) + Playwright (33) |

---

## Швидкий старт

### Через Docker — рекомендований спосіб

Піднімає весь стек одразу, разом з БД, Redis, Celery і ботом.

```bash
cp .env.docker.example .env
# у .env задати SECRET_KEY і POSTGRES_PASSWORD
docker compose up -d
docker compose ps
```

Чекаємо, доки `backend` і `db` покажуть `(healthy)`. Сайт: **http://localhost** (порт 80, через nginx).

`docker/entrypoint.sh` сам застосовує міграції та наповнює довідники — окремих команд запускати не потрібно.

### Локально, без Docker

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
python manage.py migrate

# Усі три обов'язкові: без seed_auction_fees калькулятор віддає 422
python manage.py seed_regions
python manage.py seed_rates
python manage.py seed_auction_fees

python manage.py createsuperuser
python manage.py runserver
```

Фронтенд окремим терміналом:

```bash
cd frontend
npm ci
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

Сайт: http://localhost:3000, API: http://localhost:8000.

---

## Тести

### Backend — 417 тестів

```bash
python manage.py test
```

Токен Telegram у тестах обнуляється автоматично, окремих змінних задавати не треба.

### E2E — 33 тести, Playwright

Потрібен піднятий стек. Запускати **з `frontend/`**, не з кореня репозиторію:

```bash
docker compose up -d          # з кореня
cd frontend
npx playwright test
```

| Команда | Що робить |
|---|---|
| `npm run test:e2e:ui` | UI-режим: дерево тестів, watch, trace на льоту |
| `npm run test:e2e:headed` | З видимим браузером |
| `npm run test:e2e:debug` | Інспектор з покроковим виконанням і Pick locator |
| `npm run test:e2e:report` | HTML-звіт останнього прогону |
| `npm run test:e2e:codegen` | Запис дій у код |

Детальний розбір усіх тест-кейсів — [`docs/TEST_CASES.md`](docs/TEST_CASES.md).

---

## URL-карта

| Адреса | Опис |
|--------|------|
| `/` | Головна: напрямки, етапи роботи, склад розрахунку, свіжі лоти |
| `/ua` | Каталог Україна — місцеві оголошення |
| `/local/new` | Подати оголошення |
| `/listings` | Каталог імпорту з США |
| `/calculator` | Калькулятор вартості «під ключ» |
| `/b2b` | B2B-дошка опту (тільки верифіковані дилери) |
| `/dealers/apply` | Заявка на B2B-доступ |
| `/me` | Особистий кабінет |
| `/me/messages`, `/me/deals`, `/me/favorites`, `/me/saved-searches`, `/me/notifications` | Розділи кабінету |
| `/me/shipments`, `/me/trusted-shops`, `/me/telegram`, `/me/calculations` | Логістика, партнери, бот, історія розрахунків |
| `/terms`, `/rules`, `/refund`, `/privacy`, `/cookies` | Юридичні документи |
| `/api/docs/` | Swagger UI |
| `/api/redoc/` | ReDoc |
| `/admin/` | Django Admin |

---

## Функціонал

**Каталоги.** Імпорт з США і місцеві оголошення, обидва з фільтрами й серверним рендером — вміст видно пошуковим роботам без виконання JavaScript.

**Калькулятор.** Повна розбивка: аукціонний збір (buyer fee, gate, environmental, virtual bid), логістика США, морський фрахт, доставка ЄС→UA, акциз, мито, ПДВ, пенсійний збір. Кожен розрахунок зберігає заморожений знімок застосованих ставок і курсу НБУ, тож до нього можна повернутися пізніше.

**C2C-частина.** Модерація оголошень з ремодерацією при правці суттєвих полів, антиспам із захистом телефону, скарги з діями в адмінці, підтверджені угоди й відгуки, бейдж перевіреного продавця, платне просування через LiqPay.

**Комунікації.** Внутрішні повідомлення, сповіщення в кабінеті, збережені пошуки з щоденними алертами, Telegram-бот з прив'язкою акаунта.

**Логістика.** Контейнери з семикроковим статусом від складу США до доставки, доступні тим, хто їх відстежує.

**Ролі.** buyer / dealer, верифікація дилера через заявку та адмінку. Привілеї перевіряються по `is_staff` і `is_verified_dealer` — поле `role` є категорією користувача, а не правом доступу.

---

## Ставки розмитнення

Ставки акцизу, мита та ПДВ відповідають чинному законодавству України (закони № 8487 і № 8488):

| Позиція | Ставка |
|---|---|
| Бензин ≤3000 см³ | 50 €/л |
| Бензин >3000 см³ | 100 €/л |
| Дизель ≤3500 см³ | 75 €/л |
| Дизель >3500 см³ | 150 €/л |
| Електро | 1 €/кВт·год, мито 0% |
| Мито (США) | 10% |
| ПДВ | 20% |

Формула акцизу: `базова ставка × (об'єм ÷ 1000) × кількість повних років`.

**Що дійсно орієнтовне** — логістика й аукціонні збори: вони залежать від брокера та маршруту. Відповідь калькулятора завжди містить `is_estimate: true` і попередження.

Усі ставки зберігаються в редагованих моделях адмінки з полями `valid_from`/`valid_to` — у коді їх немає.

---

## Структура

```
AUTOforYOU/
├── core/              # settings, urls, celery
├── users/             # CustomUser, JWT, заявки дилерів, TrustedShop
├── vehicles/          # Vehicle, VehicleImage — канонічна модель авто
├── pricing/           # Тарифні довідники, калькулятор, Calculation
├── listings/          # Оголошення імпорту: роздріб і опт
├── local_listings/    # C2C-оголошення України, модерація, антиспам, просування
├── shipments/         # Контейнери, TrackingEvent
├── deals/             # Угоди та відгуки, рейтинг продавця
├── messaging/         # Повідомлення між користувачами
├── notifications/     # Сповіщення в кабінеті
├── favorites/         # Обране
├── saved_searches/    # Збережені пошуки з алертами
├── reports/           # Скарги на оголошення й користувачів
├── payments/          # LiqPay: чекаут і вебхук
├── integrations/      # VIN-провайдери, імпорт лотів
├── telegram_bot/      # Бот на aiogram, вебхук, автопост у канал
├── cars/              # Застаріле, лишається до окремого рішення
├── docs/              # Тест-кейси, демо-сценарій, дорожня карта
├── frontend/          # Next.js App Router
│   ├── app/           # Сторінки й маршрути
│   ├── components/    # Компоненти
│   ├── api/           # Клієнт API
│   ├── lib/           # Типи, серверний шар запитів, згода на cookie
│   └── e2e/           # Playwright
└── nginx/, docker/    # Конфіг проксі та entrypoint-скрипти
```

---

## CI/CD

`.github/workflows/ci-cd.yml`, три обов'язкові перевірки на `main`:

| Джоб | Що робить |
|---|---|
| **Backend checks** | ruff, системні перевірки, незакомічені міграції, 417 тестів |
| **Frontend checks** | eslint, `tsc --noEmit`, збірка |
| **E2E tests** | Піднімає весь стек через docker compose з `DEBUG=false` і ганяє Playwright. HTML-звіт зберігається артефактом |

`main` захищений: прямий push заборонено, злиття тільки через PR із зеленими перевірками.

---

## Документація

| Файл | Про що |
|---|---|
| [`AUDIT.md`](AUDIT.md) | Технічний аудит проєкту та статус закриття знахідок |
| [`docs/TEST_CASES.md`](docs/TEST_CASES.md) | Розбір E2E-тестів на happy і negative path |
| [`docs/BACKEND_TESTS.md`](docs/BACKEND_TESTS.md) | Розбір backend-тестів |
| [`docs/DEMO.md`](docs/DEMO.md) | Сценарій демонстрації |
| [`DEPLOY_NOTES.md`](DEPLOY_NOTES.md) | Розгортання простою мовою |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Журнал архітектурних рішень |
| [`PROGRESS.md`](PROGRESS.md) | Журнал прогресу |
| `openapi.yaml` | Схема API, генерується `python manage.py spectacular` |

---

## Що ще не зроблено

Чесний список, щоб не було сюрпризів:

- реквізити компанії у футері й юридичних документах не заповнені;
- права на фото лотів Copart/IAAI не з'ясовані;
- сума в загальному LiqPay-чекауті приходить від клієнта — для `listing_unlock` і `listing_vip` серверного прайсу не існує, фіча незавершена;
- у калькуляторі немає доставки по Україні, хоча вона є у конкурентів;
- застаріле застосування `cars/` лишається в проєкті.

Актуальний перелік — у [Issues](https://github.com/Senpai520120/AUTOforYOU/issues).
