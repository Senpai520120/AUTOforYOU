# AUTOforYOU 🚗

> Маркетплейс авто з США під ключ для українського ринку.  
> Побудований у режимі **вайбкодингу** — Claude Sonnet як Lead Fullstack Developer.

---

## Що це

Платформа для імпорту битих авто з американських аукціонів (Copart / IAAI) до України. Покупець бачить оголошення, рахує вартість «під ключ» з митом і доставкою, відстежує контейнер. Верифіковані перекупники мають доступ до B2B-дошки з оптовими лотами.

## Стек

| Шар | Технологія |
|-----|-----------|
| Backend | Python 3.12, Django 6, DRF, SimpleJWT |
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind CSS |
| БД (dev) | SQLite |
| БД (prod) | PostgreSQL |
| Docs | drf-spectacular (Swagger / ReDoc) |

## Швидкий старт

### Backend

```bash
cd AUTOforYOU
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_rates   # заповнити тарифи
python manage.py createsuperuser
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install

# створити файл .env.local:
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm run dev
```

Відкрити: http://localhost:3000

## URL-карта

| Адреса | Опис |
|--------|------|
| http://localhost:3000 | Головна |
| http://localhost:3000/listings | Каталог авто |
| http://localhost:3000/calculator | Калькулятор «під ключ» |
| http://localhost:3000/b2b | B2B-дошка (тільки дилери) |
| http://localhost:3000/me | Особистий кабінет |
| http://localhost:8000/api/docs/ | Swagger UI |
| http://localhost:8000/admin/ | Django Admin |

## Функціонал

- **Каталог** — оголошення з фільтрами (статус, тип палива, ціна, пошук)
- **Калькулятор** — розрахунок вартості під ключ: аукціон + фрахт + розмитнення (акциз, мито, ПДВ, пенсійний збір)
- **Кабінет** — історія розрахунків, партнери (СТО/маляри/запчастини), відстеження контейнерів
- **B2B-дошка** — оптові лоти з терміновим викупом (тільки верифіковані перекупники)
- **Контейнери** — 7-кроковий прогрес (склад США → завантаження → океан → порт ЄС → автовоз → розмитнення → доставлено)
- **VIN-звіт** — заглушка (демо-дані), готова до підключення CarVertical / VinCheck
- **Ролі** — buyer / dealer / admin, верифікація перекупників через Admin

## ⚠ Важливо

Всі ставки акцизу, мита і пенсійного збору — **плейсхолдери**. Результати калькулятора позначені як `is_estimate: true` і показують банер «Тестові тарифи — демо». Перед використанням в реальних розрахунках ставки потрібно звірити з чинним законодавством України.

## Структура проєкту

```
AUTOforYOU/
├── users/          # CustomUser, JWT, TrustedShop
├── vehicles/       # Vehicle, VehicleImage
├── pricing/        # Тарифи, калькулятор, Calculation
├── listings/       # Listing (роздріб + опт)
├── shipments/      # Контейнери, TrackingEvent
├── integrations/   # VIN-провайдери (заглушки)
├── core/           # settings, urls
└── frontend/       # Next.js App Router
    ├── app/
    │   ├── listings/
    │   ├── calculator/
    │   ├── b2b/
    │   └── me/
    ├── components/
    └── api/
```

## Вайбкодинг

Весь проєкт написаний в режимі вайбкодингу разом з [Claude Code](https://claude.ai/code) (Anthropic).  
Claude виступав Lead Fullstack Developer: проєктував архітектуру, писав код, виправляв помилки, запускав сервер і тестував ендпоінти через curl.

---

*Ставки — плейсхолдери. Розрахунки — демо. Не використовувати у продакшені без верифікації тарифів.*
