# Фронт программ (фаза 4): экраны, push, service worker

Бэкенд: `docs/pwa/programs.md`, `docs/pwa/api-programs-examples.md`, `docs/pwa/garmin-push.md`. Здесь только фронт (`web/`).

## Маршруты (hash-роутер)

| Маршрут | Экран | Файл |
|---|---|---|
| `#/programs` | вкладка «Программы»: «Мои программы» (GET `/api/enrollments`) + корень каталога (Кроссфит / ТА / Бег) | `screens/programs/Catalog.tsx` |
| `#/programs/node/:slug` | уровень каталога (спорт или система), хлебные крошки; `planned`-узел открывается заглушкой «Раздел наполняется» | `Catalog.tsx` |
| `#/programs/p/:slug` | карточка программы: описание, структура недель, опорные веса с источником, форма записи | `ProgramCard.tsx` |
| `#/programs/my/:id` | подписка: прогресс, «сегодня», недели, опорные, тренд «максимум дня», пауза/возобновить/отмена | `Enrollment.tsx` |
| `#/programs/session/:sid` | экран у помоста | `Bench.tsx` |
| `#/program`, `#/garmin` | алиасы под ссылки из push (`/app/#/program`, `/app/#/garmin`): редирект на `/programs` и `/profile/garmin` | `App.tsx` |

Вложенные маршруты собраны в `screens/programs/index.tsx` (`ProgramsRoutes`), в `App.tsx` это одна строка `programs/*`.
В общих файлах правки минимальные: `App.tsx` (3 строки маршрутов + импорт), `Shell.tsx` (вкладка «Программы» в `TABS`,
`<NoticeBanners/>` в `Layout`), `Profile.tsx` (`<PushToggle/>`), `i18n/index.tsx` (слияние `programs.json`), `api/client.ts`
(`ApiError.code` и `ApiError.body`, чтобы достать `items` из 422).

## Компоненты и модули

- `api/programs.ts` типы ответов и вызовы (`programsApi`, `pushApi`), `NeedsInputError` (422 `needs_input` с `items`), `localToday()`
  (клиент шлёт `?today=` с локальной датой устройства), `newId()`.
- `api/pushClient.ts` `urlBase64ToUint8Array` (VAPID base64url), `enablePush` / `disablePush` / `currentPushState`.
- `screens/programs/tree.ts` разбор дерева (`isPlanned`, `isOpenableProgram`, `visibleChildren`, `pathTo`), `sourceKey`, `loc()`.
- `screens/programs/parts.tsx` `ReferenceRow` (лифт, кг, откуда цифра) и `Crumbs`.
- `enrollForm.ts` тело `POST enroll` (ручные максы -> `base_maxes`, уровень -> `level`), готовность формы.
- `benchState.ts` локальное состояние сессии (localStorage `fepra.bench.<sid>`), `overlayLocal`, `pendingPuts`, `diffPlanned`, `groupDiffs`.
- `rest.ts` таймер отдыха (`restEndAt`, `useCountdown`), вибрация/звук (`alertRestOver`, `primeAudio`), `useWakeLock`.
- `Notices.tsx` баннеры `GET /api/notices` (для `garmin_*` кнопка на экран Garmin), `PushToggle.tsx` переключатель в Профиле.
- `src/sw.ts` + `src/push-utils.ts` service worker.
- `i18n/programs.json` RU и EN (`{ru: {...}, en: {...}}`), ключи `pg.*`, `push.*`, `notice.*`, `tab.programs`.

## Как устроены ключевые вещи

**Каталог.** Дерево берётся из `GET /api/programs/tree`. Узлы `soon` / `planned` рисуются приглушённо с меткой «скоро».
Спорт и система с `planned` ведут на заглушку (внутри те же приглушённые узлы), planned-программа не ссылка
(`aria-disabled`). `hidden` не показывается. Активная программа ведёт на карточку.

**Опорные веса.** `ReferenceRow` показывает источник: `best` («Ваш максимум, дата», бейдж «устарел» при `stale`),
`derived` («Оценка от: лифт» + «оценка, уточнится тест-сессией»), `starter` («Стартовый уровень «обычный»»), `needs_input`, а также
`user` и `test` (после записи и тест-сессии). Для `needs_input` форма записи показывает три уровня
(осторожный / обычный / опытный, кг по каждому лифту из `options`) или ручной ввод максимума. Уровень один на всю программу
(`level`), ручные значения идут в `base_maxes`. Кнопка «Начать программу» -> `POST /api/programs/{slug}/enroll`
с клиентским `id` (повтор безопасен). Если сервер вернул 422 `needs_input`, форма перерисовывается вопросами из `items`.
Если `needs_test` непустой, показывается «Первая тренировка будет тестом максимума».

**Экран у помоста.**
- Чек-ин (энергия 1..5, сустав, устал, плохо спал, болел) -> `POST checkin`, ответ (полный вид сессии) заменяет план, плашка `why`.
  Можно пропустить.
- Подход: крупная карточка «текущего» подхода, кнопки «✓ Сделал» / «✗ Не вышло» (высота 64px), поле «сделал другой вес»
  (вес уходит в `done_kg` любой из кнопок). Отмеченный подход можно поправить тапом по строке.
- «Не вышло»: `PUT` с `ok:false`. В ответе только `changed` (id подходов) и `why`, новые веса приходят повторным `GET` сессии;
  над списком показывается причина и «было -> стало» (одинаковые строки сворачиваются в `×N`). В тест-сессии правило не действует,
  `changed` пуст.
- Таймер отдыха: после отметки подхода `rest_sec` **этого** подхода (в шаблонах отдых стоит после подхода: чем тяжелее, тем дольше).
  Хранится момент окончания (`restEnd`, epoch ms) и пересчитывается от `Date.now()` на каждом тике и при `visibilitychange`, поэтому
  блокировка экрана его не сбивает. Вибрация и звук по окончании, если платформа разрешает (звук включается жестом первой отметки).
  «Пропустить» гасит. Таймер переживает перезагрузку (лежит в localStorage).
- Wake Lock: `navigator.wakeLock.request('screen')`, переподхват при возврате во вкладку. Без API показывается подсказка отключить автоблокировку
  (видео-фолбэк в стиле NoSleep не делали).
- Локальное состояние: отметка сначала пишется в localStorage с `pending:true`, затем уходит `PUT`; ответ снимает `pending`. При загрузке
  сервер — источник правды, но неподтверждённые локальные отметки доотправляются (`pendingPuts`), потом сессия перечитывается. Записи старше 7 дней
  чистятся. Без сети отметки остаются в телефоне, плашка «неотправленных отметок N» с «Повторить»; при `online` уходят сами.
- Тест-сессия (`kind=test`): бейдж, пояснение про лесенку до максимума дня, подписи «попытка», предупреждение при `postpone_advised`.
- Завершение: RPE 1..10 + самочувствие 1..5 -> `POST finish` с постоянным `activity_id` (UUID хранится локально, повтор идемпотентен).
  Итог: новые максимумы, «Обновить опорные?» (`POST refresh-base` со списком лифтов), `base_updated`, признак завершения программы.
  При повторном открытии завершённой сессии итог берётся идемпотентным `POST finish {}` (`already: true`).

**Тренд.** На карточке подписки вкладки по лифтам, `GET /api/lifts/{lift}/trend`, Chart.js (линия), подпись направления и дельта.

**Push.** Профиль -> «Уведомления»: `GET /api/push/key` (503 = на сервере нет VAPID) -> `Notification.requestPermission` ->
`pushManager.subscribe({applicationServerKey})` -> `POST /api/push/subscribe` (`PushSubscription.toJSON()`); выключение: `POST unsubscribe` и
`subscription.unsubscribe()`. На iPhone работает только из установленной на экран Домой PWA (без неё показывается «не поддерживаются»).

**Service worker.** Переведён с `generateSW` на `injectManifest` (`vite.config.ts`: `strategies: 'injectManifest'`, `src/sw.ts`).
Предкэш оболочки и `NavigationRoute` с denylist `/api/` — как раньше, runtime-кэша нет. Добавлены `push`
(payload JSON `title/body/url/tag`, не-JSON текст показывается как тело) и `notificationclick` (фокус уже открытого окна `/app/` и переход на `url`,
иначе `openWindow`). URL из уведомления пропускается через `targetUrl`: только свой origin и путь под `/app/`, остальное ведёт на `/app/`.
Тип WebWorker не подключался (конфликт с DOM), нужный минимум описан в `sw.ts`. Сборка кладёт `sw.js` в classic-формате.

**Баннеры.** `GET /api/notices?unread=1` в `Layout` (над экраном). Для `garmin_*` кнопка «Войти в Garmin» -> `/profile/garmin` и `POST read`; «Скрыть» тоже
помечает прочитанным.

## Проверки

```bash
cd web && npm run build && npx vitest run && npm run lint   # затем git checkout -- ../src/tjapp/static/app (статику собирает интеграция)
```
Тесты: `test/programs-logic.test.ts` (дерево, planned, источник веса, форма записи, диф пересчёта, localStorage, VAPID, payload push),
`programs-rest.test.tsx` (таймер на fake timers, «экран был заблокирован»), `programs-screens.test.tsx` (каталог, запись с 422, экран у помоста
целиком: «Сделал», «Не вышло», перезагрузка с доотправкой, чек-ин, завершение, Wake Lock, баннеры), `programs-i18n.test.ts`
(RU/EN совпадают, статические ключи из кода есть в словарях).

Dev: push key отвечает 503, пока нет `FEPRA_VAPID_*`; чтобы попробовать подписку, задай пару VAPID в окружении.

## Найденные проблемы бэкенда

1. **`sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`** (500, плавающая). Зависимость `_con()`
   в `routes/programs.py`, `notices.py`, `push.py` (и аналогичных) — синхронный генератор: FastAPI выполняет его вход и хендлер в разных потоках
   threadpool. `tjbot.db.connect` не ставит `check_same_thread=False`. Лечится
   в `tjbot.db.connect` (`check_same_thread=False`, соединение на запрос, не общее) либо `async def`-зависимостью. Проверить на проде: воспроизводится при
   параллельных запросах.
2. Нет списка сессий подписки (`GET /api/enrollments/{id}/sessions`), поэтому «календарь сессий» на карточке подписки — полоса недель шаблона
   с подсветкой текущей (по `next_session.week`) и общий прогресс `sessions.done/total`, без дат каждой сессии.
3. Нет чтения предложения «обновить опорные?» вне `finish`: `refresh` приходит только в ответе `finish`. На карточке подписки кнопка
   «Обновить опорные по новым максимумам» вызывает `POST refresh-base` без списка (применяет всё, что предложит сервис) и показывает `refreshed`.
   Лучше добавить `refresh` в `GET /api/enrollments/{id}` или отдельный GET.
4. Ссылки push: `garmin_alerts` шлёт `/app/#/garmin` (на фронте алиас на `/profile/garmin`), `notify_program_today` — `/app/#/program` (алиас на
   `/programs`), `notify_rest_over` — `/app/#/workout` (маршрута нет: экран записи тренировки в другой ветке; после слияния сделать алиас
   или сменить url на `/app/#/programs/session/<sid>`).
5. В `SetIn` нельзя явно сбросить отметку подхода (`ok: null` неотличим от «не передано»), поэтому «вернуть подход в неотмеченный» не сделано:
   правка отметки переписывает её значением «сделал / не вышло».

## Осталось

- Внеплановые подходы (`extra_sets` только показываются, добавления в UI нет), правка `weekdays` при записи.
- Видео-фолбэк для Wake Lock на iOS < 16.4.
- Серверный push «отдых закончен» (`notify_rest_over`) фронт не вызывает: таймер локальный.
- Ручная проверка на реальном iPhone: push из PWA, вибрация (iOS Safari её не поддерживает), звук таймера при заблокированном экране.
