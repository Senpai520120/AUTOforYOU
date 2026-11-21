# Дизайн-система AUTOforYOU (задача 11.13)

Источники: `docs/SPEC_IMPORT_CATALOG_2026-11.md` (модуль H), `docs/design/research/01_*.md`, `02_*.md`. Гайды modern-web-guidance: `.mwg/` (color, dark-mode, typography, visually-stable-font-fallbacks, icons).

## Токены

Файл `frontend/app/globals.css`: формат shadcn, цвета в OKLCH, `:root` (светлая тема) и `.dark`, маппинг в Tailwind через `@theme inline`. Токены задаём вручную (без GUI tweakcn), контраст проверен расчётом (см. ниже).

| Токен | Значение (light) | Роль |
|---|---|---|
| `--background` / `--foreground` | #F4F5F7 / #111418 | фон страницы, основной текст |
| `--card`, `--popover` | #FFFFFF (текст #111418) | поверхности |
| `--primary` / `--primary-foreground` | #111418 (графит) / #FFFFFF | основные кнопки |
| `--secondary`, `--muted` | #F3F4F6 | вторичные поверхности |
| `--muted-foreground` | #4B5563 | вторичный текст |
| `--accent` / `--accent-foreground` | #C6F432 (лайм) / #111418 | главные CTA, бейджи ТОП; ТОЛЬКО заливка |
| `--link` | #3F6212 (тёмно-оливковый) | ссылки в тексте (`text-link`), фирменные иконки |
| `--destructive` | `oklch(0.505 0.19 27.5)` (#b91c1c) | ошибки, удаление |
| `--success`, `--warning` (+`-foreground`) | green-700 / amber-400 | статусы (всегда вместе с иконкой или текстом, WCAG 1.4.1) |
| `--border` | #E5E7EB | декоративные границы (карточки, разделители): порога 3:1 нет |
| `--input` | #6B7280 | граница полей формы (порог 3:1) |
| `--ring` | #3F6212 | фокус |
| `--header`, `--header-foreground` | #111418 / #FFFFFF | шапка (тёмная в обеих темах) |
| `--footer`, `--footer-foreground`, `--footer-muted` | #111418 / #D1D5DB / #A8B0BA | подвал |
| `--radius` | `0.625rem` | базовый радиус; `sm/md/lg/xl` считаются от него |

Тёмная тема: токены `.dark` (фон #111418, карточки #1B1F25, текст #F4F5F7, primary — лайм с графитовым текстом, синего нет) определены, но НЕ включены (нет ни класса `dark` на `<html>`, ни `prefers-color-scheme`). На `:root` явно `color-scheme: light`. Решение 11.14 (2026-11-21): тёмная тема НЕ включается (см. раздел «Тёмная тема: решение 11.14»).

Старые переменные (`--bg`, `--surface`, `--text`, `--muted`, `--danger`, `--primary-dark`) удалены; использований в коде (`var(--…)`, CSS-модули, arbitrary values) не было, страницы на хардкод-классах `slate-*`/`blue-*` переводит 11.14.

## Контраст

Расчёт: OKLCH -> linear sRGB -> относительная яркость WCAG 2.x; скрипт читает токены прямо из `globals.css`. Пороги: текст 4.5:1 (1.4.3), границы полей и фокус 3:1 (1.4.11). Не прошедших пар нет. Палитра «Графіт і лайм» пересчитана 2026-11-21; непрошедших пар нет.

| Тема | Пара | Токены | Контраст | Порог | Результат |
|---|---|---|---|---|---|
| light | Основний текст | `foreground` / `background` | 16.93 | 4.5 | OK |
| light | Текст у картці | `card-foreground` / `card` | 18.46 | 4.5 | OK |
| light | Вторинний текст (muted) на фоні | `muted-foreground` / `background` | 6.93 | 4.5 | OK |
| light | Вторинний текст на muted | `muted-foreground` / `muted` | 6.87 | 4.5 | OK |
| light | Вторинний текст на картці | `muted-foreground` / `card` | 7.56 | 4.5 | OK |
| light | Primary: текст кнопки | `primary-foreground` / `primary` | 18.46 | 4.5 | OK |
| light | Secondary: текст | `secondary-foreground` / `secondary` | 16.78 | 4.5 | OK |
| light | Accent (лайм): текст | `accent-foreground` / `accent` | 14.39 | 4.5 | OK |
| light | Destructive: текст | `destructive-foreground` / `destructive` | 6.48 | 4.5 | OK |
| light | Success: текст | `success-foreground` / `success` | 5.02 | 4.5 | OK |
| light | Warning: текст | `warning-foreground` / `warning` | 11.06 | 4.5 | OK |
| light | Помилка (destructive) як текст на фоні | `destructive` / `background` | 5.94 | 4.5 | OK |
| light | Помилка (destructive) як текст на картці | `destructive` / `card` | 6.48 | 4.5 | OK |
| light | Success як текст на фоні | `success` / `background` | 4.60 | 4.5 | OK |
| light | Посилання (link) на фоні | `link` / `background` | 6.48 | 4.5 | OK |
| light | Посилання (link) на картці | `link` / `card` | 7.07 | 4.5 | OK |
| light | Шапка: текст | `header-foreground` / `header` | 18.46 | 4.5 | OK |
| light | Шапка: лайм (логотип, hover, каталог) | `accent` / `header` | 14.39 | 4.5 | OK |
| light | Шапка: фокус (світла обводка) | `header-foreground` / `header` | 18.46 | 3 | OK |
| light | Підвал: текст | `footer-foreground` / `footer` | 12.54 | 4.5 | OK |
| light | Підвал: приглушений текст | `footer-muted` / `footer` | 8.43 | 4.5 | OK |
| light | Підвал: фокус (світла обводка) | `header-foreground` / `footer` | 18.46 | 3 | OK |
| light | Межа поля (input) на фоні | `input` / `background` | 4.43 | 3 | OK |
| light | Межа поля (input) на картці | `input` / `card` | 4.83 | 3 | OK |
| light | Фокус (ring) на фоні | `ring` / `background` | 6.48 | 3 | OK |
| light | Фокус (ring) на картці | `ring` / `card` | 7.07 | 3 | OK |
| light | Primary (кнопка) на фоні — межа елемента | `primary` / `background` | 16.93 | 3 | OK |
| light | Лайм (accent) як заливка на шапці — межа елемента | `accent` / `header` | 14.39 | 3 | OK |
| light | Декоративна межа (border) на фоні | `border` / `background` | 1.13 | — | — |
| dark | Основний текст | `foreground` / `background` | 16.93 | 4.5 | OK |
| dark | Текст у картці | `card-foreground` / `card` | 15.16 | 4.5 | OK |
| dark | Вторинний текст (muted) на фоні | `muted-foreground` / `background` | 8.43 | 4.5 | OK |
| dark | Вторинний текст на muted | `muted-foreground` / `muted` | 6.49 | 4.5 | OK |
| dark | Вторинний текст на картці | `muted-foreground` / `card` | 7.55 | 4.5 | OK |
| dark | Primary: текст кнопки | `primary-foreground` / `primary` | 14.39 | 4.5 | OK |
| dark | Secondary: текст | `secondary-foreground` / `secondary` | 13.03 | 4.5 | OK |
| dark | Accent (лайм): текст | `accent-foreground` / `accent` | 14.39 | 4.5 | OK |
| dark | Destructive: текст | `destructive-foreground` / `destructive` | 6.68 | 4.5 | OK |
| dark | Success: текст | `success-foreground` / `success` | 8.55 | 4.5 | OK |
| dark | Warning: текст | `warning-foreground` / `warning` | 11.06 | 4.5 | OK |
| dark | Помилка (destructive) як текст на фоні | `destructive` / `background` | 6.68 | 4.5 | OK |
| dark | Помилка (destructive) як текст на картці | `destructive` / `card` | 5.99 | 4.5 | OK |
| dark | Success як текст на фоні | `success` / `background` | 10.58 | 4.5 | OK |
| dark | Посилання (link) на фоні | `link` / `background` | 14.39 | 4.5 | OK |
| dark | Посилання (link) на картці | `link` / `card` | 12.89 | 4.5 | OK |
| dark | Шапка: текст | `header-foreground` / `header` | 18.46 | 4.5 | OK |
| dark | Шапка: лайм (логотип, hover, каталог) | `accent` / `header` | 14.39 | 4.5 | OK |
| dark | Шапка: фокус (світла обводка) | `header-foreground` / `header` | 18.46 | 3 | OK |
| dark | Підвал: текст | `footer-foreground` / `footer` | 12.54 | 4.5 | OK |
| dark | Підвал: приглушений текст | `footer-muted` / `footer` | 8.43 | 4.5 | OK |
| dark | Підвал: фокус (світла обводка) | `header-foreground` / `footer` | 18.46 | 3 | OK |
| dark | Межа поля (input) на фоні | `input` / `background` | 4.94 | 3 | OK |
| dark | Межа поля (input) на картці | `input` / `card` | 4.42 | 3 | OK |
| dark | Фокус (ring) на фоні | `ring` / `background` | 14.39 | 3 | OK |
| dark | Фокус (ring) на картці | `ring` / `card` | 12.89 | 3 | OK |
| dark | Primary (кнопка) на фоні — межа елемента | `primary` / `background` | 14.39 | 3 | OK |
| dark | Лайм (accent) як заливка на шапці — межа елемента | `accent` / `header` | 14.39 | 3 | OK |
| dark | Декоративна межа (border) на фоні | `border` / `background` | 1.39 | — | — |

Строка «Декоративная граница» не имеет порога: `--border` (1.18:1) используется только для карточек и разделителей, не для полей. У полей формы граница `--input`.

## Шрифт

Manrope (Google Fonts, OFL) через `next/font/google` в `frontend/app/layout.tsx`: `subsets: ['latin','cyrillic']`, `display: 'swap'`, переменная `--font-manrope`, в `@theme inline` она становится `--font-sans` (первым в стеке, затем системные). `adjustFontFallback` не отключён (по умолчанию включён): Next генерирует fallback с `size-adjust`, поэтому подмена шрифта без сдвига вёрстки (CLS). `font-size-adjust: from-font` не добавлялся: он дублировал бы `size-adjust`. Размеры шрифта — в rem, `line-height` без единиц.

## Иконки

`lucide-react` (ISC), `iconLibrary: lucide` в `components.json`. Одна толщина линии: `ICON_STROKE = 2` из `frontend/lib/utils.ts`, передавать как `strokeWidth={ICON_STROKE}`. Размер — `size-5` (в строке) или `size-6` (кнопка меню), `aria-hidden="true"` на декоративных. Иконка-кнопка обязана иметь `aria-label`. Контраст иконок >= 3:1 (токены выше).

## Правила использования компонентов

- Новые и переписываемые элементы формы, кнопки, карточки, вкладки, sheet, skeleton, badge, separator — из `@/components/shadcn/*` (button, card, input, label, textarea, select, badge, separator, sheet, skeleton, tabs). Добавление: `npx shadcn@latest add <имя> --yes` из `frontend/`; алиас `ui` указывает на `@/components/shadcn`, НЕ на `components/ui`.
- Свои компоненты в `frontend/components/ui/` (PascalCase: `Badge`, `Skeleton`, `Modal`, `ConfirmDialog`, `FlashMessage`, `CookieBanner`…) остаются, пока 11.14 не заменит их по месту. Файлы shadcn (lowercase) и свои (PascalCase) в одной папке не уживаются на Windows, поэтому папки разные.
- Ссылки в тексте — `text-link` (оливковый), не `text-primary` (графит неотличим от текста); кнопки — `Button`.
- Цвета только токенами (`bg-primary`, `text-muted-foreground`, `border-input`), не `slate-*`/`blue-*`/hex.
- Правки сгенерированных файлов shadcn (сознательные): высоты `min-h-*` вместо `h-*` (текст не обрезается при увеличенных интервалах, WCAG 1.4.12; кнопки и поля по умолчанию 44 px), сплошной фокус `ring-2 ring-ring` вместо полупрозрачного `ring-ring/50` (иначе < 3:1). При повторном `add` с перезаписью эти правки возвращать.
- Фокус: глобальное правило в `globals.css` (`outline: 2px solid var(--ring)`, поведение 10.28), для shadcn-компонентов — собственный `ring`. На тёмных блоках (шапка, подвал) атрибут `data-on-dark` переключает обводку на светлую. `@media (forced-colors: active)`: обводка `Highlight`.
- Тёмная тема: отложена (решение 11.14); при правках проверять оба набора токенов.

## Storybook (11.15)

- Запуск (из `frontend/`): `npm run storybook` (http://localhost:6006), сборка — `npm run build-storybook` (выход `storybook-static/`, в git не попадает; в CI собирается шагом «Build Storybook»).
- Фреймворк `@storybook/nextjs-vite`, аддоны a11y и docs. Конфиг — `frontend/.storybook/`. Токены берутся из `app/globals.css`.
- Stories лежат рядом с компонентами (`*.stories.tsx`); данные — `frontend/stories/fixtures/` (фейковые, без ПДн). Запросы к API подменены в `preview.ts`, сети нет.
- Шрифт Manrope в Storybook не грузится (next/font), используется системный fallback из `--font-sans`.
- Кэш Vite — `frontend/node_modules/.cache/storybook-vite` (диск D).
- Новый компонент в `components/shadcn` — добавлять рядом `<name>.stories.tsx`.
- Визуальные снимки страниц: `e2e/visual.spec.ts`, инструкция по съёмке базы в шапке файла и в PROGRESS.

## Лицензии

- shadcn/ui — MIT: https://github.com/shadcn-ui/ui/blob/main/LICENSE.md
- lucide — ISC: https://lucide.dev/license
- Manrope — SIL OFL 1.1: https://github.com/sharanda/manrope/blob/master/OFL.txt (https://fonts.google.com/specimen/Manrope/license)
- Radix UI (зависимость shadcn) — MIT; tw-animate-css — MIT; class-variance-authority — Apache-2.0; clsx — MIT; tailwind-merge — MIT.

## Тёмная тема: решение 11.14

Не включаем. На токены переведены главная, `/prigon`, калькулятор, каталог `/ua`, карточка объявления `/local/[id]`, форма заявки и общие `components/ui/*`. Остальной сайт ещё на хардкоде `slate/blue/gray` (в части файлов и `red/green/amber`): с классом `dark` он стал бы смесью светлых и тёмных блоков, а контраст `.dark` для этих страниц не проверен. Токены `.dark` и их контраст посчитаны (таблица выше), включать после перевода остатка и axe-прогона в тёмной теме.

Остаток (53 файла по `grep -rlE "(bg|text|border)-(slate|blue|gray)-[0-9]" app components`, было 80): `app/{about,b2b,cookies,dealers/apply,error,how-it-works,not-found,login,register,password-reset,password-reset/confirm,privacy,refund,rules,terms,verify-email}`, `app/listings/{ListingsGrid,WholesaleHint,loading,page}`, `app/local/new`, `app/local/[id]/edit`, `app/me/*` (MeDashboard, calculations, data, deals, favorites, leads, loading, local-listings, messages, notifications, profile, saved-searches, security, shipments, telegram, trusted-shops), `app/sellers/[id]`, `components/{PhoneVerifyTelegram,c2c/ComingSoon,content/FaqBlock,legal/LegalPage}`, `components/leads/{AccessDenied,BrokerLeadCard,BrokerLeadList,LeadStatusBadge}`, `components/listings/{ListingCard,ListingDetail,ListingFilters}`, `components/local/{LocalListingForm,PhotoUploadBlock,PromoteModal}`.

## Палітра Графіт і лайм (2026-11-21, рішення власника)

Замінила синьо-бурштинову палітру. Графіт (#111418) — шапка, підвал, основні кнопки (`primary`); лайм (#C6F432) — лише ЗАЛИВКА: головні CTA і бейджі ТОП з графітовим текстом (14.39). Лайм НЕ можна ставити кольором тексту чи іконки на світлому фоні (1.18:1); на графітовій шапці лайм-текст дозволений (14.39). Ссылки в тексте и фирменные иконки — оливковый `--link` (#3F6212; 6.48 на фоне, 7.07 на белом); фокус — `--ring` того же цвета, на тёмных блоках (`data-on-dark`) — белая обводка (10.36+ на графите). Шапка и hero главной — плоский графит (градиент `header → primary` убран). Страницы на хардкоде `blue-*` (остаток 11.14) перейдут отдельной задачей.
