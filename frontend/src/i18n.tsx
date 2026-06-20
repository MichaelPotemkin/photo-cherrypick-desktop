import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

// Lightweight i18n (no dependency): a flat key->string dict per language, a `t(key, vars)` helper
// with {placeholder} interpolation, and a localStorage-persisted language choice. Backend-generated
// vocab (scoring reasons, axis names, shot scales) is translated through the same dict via the
// tReason/tAxis/tScale helpers, falling back to the original English when a key is unknown.

export type Lang = "en" | "uk" | "ru";

type Dict = Record<string, string>;

const en: Dict = {
  // --- home / session input ---
  app_title: "Photo Cherrypick",
  home_tagline:
    "Pick a folder of photos (RAW or JPEG) to analyze and cull. Everything stays on your computer — nothing is uploaded.",
  choose_folder: "Choose folder…",
  analyze_folder: "Analyze folder",
  choose_folder_title: "Browse for a folder of photos on your computer",
  analyze_folder_title: "Analyze the folder and start culling — nothing leaves your computer",
  analyzing: "Analyzing…",
  failed_create: "Failed to create session",
  recent_sessions: "Recent sessions",
  n_photos: "{n} photos",
  status_analyzing: "analyzing {done}/{total}…",
  status_queued: "queued…",
  status_error: "error",
  status_kept_maybe: "{fav} kept · {maybe} maybe",
  delete_session: "Delete session",
  delete_confirm:
    'Delete "{name}"? This removes the session and its cull decisions (your photo files are not touched).',
  close: "Close",

  // --- how-to guide ---
  help_button: "How to use",
  help_title: "How to use Photo Cherrypick",
  help_loading_hint:
    "While your photos analyze, here's how the workflow goes — your decisions are saved as you make them.",
  help_intro:
    "Analyze a folder once; the three passes below all work on that same set of photos. Your ★ keep / ? maybe / 🗑 trash decisions are saved and carry across every pass — you never re-import.",
  help_pass1_title: "Pass 1 · Cull (Burst)",
  help_pass1_body:
    "Each group is a burst of near-identical frames. Pick the keeper from each: ★ keep, ? maybe, 🗑 trash — keys f / m / x (u to undo). The ✨ suggested frame is the algorithm's best guess; trust your own eye.",
  help_pass2_title: "Pass 2 · Group (Scene)",
  help_pass2_body:
    "Switch to Scene to see your keepers regrouped by scene and outfit, ignoring time — handy for building a gallery or Instagram set. Trashed photos are left out.",
  help_pass3_title: "Pass 3 · Arrange (Feed)",
  help_pass3_body:
    "Feed lays your ★ favorites into a balanced grid — alternating shot scale, scenes spread out — so you can see how the set reads together.",
  help_download:
    "When you're happy, Download picks saves your favorites and maybes as a ZIP of the untouched original files. Nothing is altered, moved, or uploaded.",
  help_got_it: "Got it",

  // --- header ---
  new_session: "New session",
  rename_session: "Rename session",
  session_name: "Session name",
  sub_bursts: "{n} bursts",
  sub_scenes: "{n} scenes",
  sub_feed: "{n} in feed",
  aria_grouping_mode: "Grouping mode",
  aria_language: "Language",
  mode_burst: "Burst",
  mode_scene: "Scene",
  mode_feed: "Feed",
  mode_burst_title:
    "Burst — near-duplicate frames shot in quick succession. The first culling pass: pick the keeper from each burst.",
  mode_scene_title:
    "Scene — all similar shots (same setting & outfit) grouped together, ignoring time. The second pass: build a gallery / Instagram set from your keepers.",
  mode_feed_title:
    "Feed — your favorites arranged into a balanced gallery/Instagram grid: alternating shot scale, scenes spread out. The final pass: see how the set reads as a grid.",
  undecided: "{n} undecided",
  kept: "★ {n} kept",
  maybe_pill: "? {n} maybe",
  trash_pill: "🗑 {n} trash",
  hide_sorted: "Hide sorted",
  show_all: "Show all",
  hide_sorted_title: "Hide photos you've already sorted (kept, maybe, or trashed)",
  show_all_title: "Show every photo, including the ones you've already sorted",
  accept_picks: "✓ Accept picks",
  accept_confirm: "Favorite {n} suggested picks?",
  confirm: "Confirm",
  cancel: "Cancel",
  accept_title: "Favorite the algorithm's best-of-burst pick in every group still undecided",
  accept_none_title: "No undecided suggestions left to accept",
  download_picks: "⬇ Download picks",
  download_disabled_title: "Mark some photos favorite or maybe first",
  download_title: "Download your picks (favorites + maybe) as a ZIP of the original files",

  // --- in-app updater (bottom of screen) ---
  version_label: "version {v}",
  update_downloading: "Downloading update",
  update_ready: "Update ready",
  update_relaunch_tip: "Restart now to finish updating",

  // --- groups ---
  group: "Group",
  label_burst_pick: "{n} in burst — pick one",
  label_single: "single shot",
  label_scene: "{n} in scene",
  label_unique: "unique look",
  close_call: "⚖ too close to call",
  close_call_title:
    "The top two frames score within a hair of each other — the algorithm isn't confident here. Trust your own eye.",
  empty_hidden: "Nothing to show. Try turning off “Hide sorted”.",

  // --- card / lightbox ---
  badge_suggested: "✨ suggested",
  badge_kept: "★ kept",
  badge_maybe: "? maybe",
  badge_trash: "🗑 trash",
  btn_fav: "★ fav",
  btn_maybe: "? maybe",
  btn_trash: "🗑 trash",
  btn_undo: "↩ undo",
  // icon-only labels for the dense per-card action row (locale-independent, equal width)
  btn_fav_short: "★",
  btn_maybe_short: "?",
  btn_trash_short: "🗑",
  btn_undo_short: "↩",
  mark_favorite: "Mark favorite",
  remove_favorite: "Remove favorite",
  mark_maybe: "Mark maybe",
  remove_maybe: "Remove maybe",
  mark_trash: "Trash",
  remove_trash: "Remove trash",
  clear_label: "Clear label",
  score: "score {n}",
  bw: "b&w",
  axes_title: "Axes",
  prev_group: "↑ prev group",
  next_group: "next group ↓",
  prev_group_title: "Previous group (↑)",
  next_group_title: "Next group (↓)",
  prev_photo_title: "Previous photo (←)",
  next_photo_title: "Next photo (→)",
  close_esc: "Close (Esc)",
  hover_zoom: "Hover to zoom — move the cursor to look around",
  suggested_caption: "✨ suggested",

  // --- feed ---
  feed_planning: "Planning feed…",
  feed_failed: "Failed to plan feed",
  feed_empty_pre: "Mark some photos ",
  feed_empty_strong: "★ favorite",
  feed_empty_post: " to plan your feed.",
  feed_hint:
    "{n} favorites arranged for a balanced grid — alternating shot scale, scenes spread out. Reading order is top-left first.",

  // --- progress ---
  status_label: "Status",
  st_pending: "pending",
  st_processing: "processing",
  st_ready: "ready",
  st_err: "error",
  photos_pct: "{done} / {total} photos ({pct}%)",

  // --- session view errors ---
  failed_load_session: "Failed to load session",
  back_new_session: "← New session",
  analysis_failed: "Analysis failed",
  unknown_error: "Unknown error",
  loading: "Loading…",
  loading_groups: "Loading groups…",
  failed_load_groups: "Failed to load groups",

  // --- scoring reasons (the fixed vocabulary from pipeline/score.py) ---
  "reason:eyes open": "eyes open",
  "reason:all eyes open": "all eyes open",
  "reason:sharp eyes": "sharp eyes",
  "reason:smiling": "smiling",
  "reason:everyone smiling": "everyone smiling",
  "reason:eye contact": "eye contact",
  "reason:well exposed": "well exposed",
  "reason:catchlight": "catchlight",
  "reason:sunglasses — judged on pose & expression": "sunglasses — judged on pose & expression",

  // --- category bars (PhotoCard) ---
  "cat:Focus": "Focus",
  "cat:Subject": "Subject",
  "cat:Compos": "Compos",
  "cat:Expo": "Expo",
  "cat:Aesth": "Aesth",

  // --- axes (lightbox) ---
  "axis:eye sharpness": "eye sharpness",
  "axis:face sharpness": "face sharpness",
  "axis:subject vs bg": "subject vs bg",
  "axis:exposure": "exposure",
  "axis:contrast": "contrast",
  "axis:eyes open": "eyes open",
  "axis:expression": "expression",
  "axis:eye contact": "eye contact",
  "axis:rule of thirds": "rule of thirds",
  "axis:headroom": "headroom",
  "axis:framing/size": "framing/size",
  "axis:clean bg": "clean bg",
  "axis:aesthetic": "aesthetic",

  // --- shot scale (feed) ---
  "scale:close": "close",
  "scale:medium": "medium",
  "scale:wide": "wide",
};

const uk: Dict = {
  app_title: "Photo Cherrypick",
  home_tagline:
    "Оберіть теку з фото (RAW або JPEG) для аналізу та відбору. Усе залишається на вашому комп’ютері — нічого не завантажується в інтернет.",
  choose_folder: "Обрати теку…",
  analyze_folder: "Аналізувати теку",
  choose_folder_title: "Огляд тек із фото на вашому комп’ютері",
  analyze_folder_title: "Проаналізувати теку й почати відбір — нічого не залишає ваш комп’ютер",
  analyzing: "Аналіз…",
  failed_create: "Не вдалося створити сесію",
  recent_sessions: "Останні сесії",
  n_photos: "{n} фото",
  status_analyzing: "аналіз {done}/{total}…",
  status_queued: "у черзі…",
  status_error: "помилка",
  status_kept_maybe: "{fav} обрано · {maybe} під питанням",
  delete_session: "Видалити сесію",
  delete_confirm:
    "Видалити «{name}»? Це прибере сесію та її рішення щодо відбору (ваші файли фото не зачіпаються).",
  close: "Закрити",

  // --- how-to guide ---
  help_button: "Як користуватися",
  help_title: "Як користуватися Photo Cherrypick",
  help_loading_hint:
    "Поки фото аналізуються, ось як влаштований процес — ваші рішення зберігаються автоматично.",
  help_intro:
    "Проаналізуйте теку один раз; усі три проходи нижче працюють із тим самим набором фото. Ваші позначки ★ обрати / ? під питанням / 🗑 видалити зберігаються й переходять між усіма проходами — повторно завантажувати не потрібно.",
  help_pass1_title: "Прохід 1 · Відбір (Серія)",
  help_pass1_body:
    "Кожна група — це серія майже однакових кадрів. Оберіть найкращий: ★ обрати, ? під питанням, 🗑 видалити — клавіші f / m / x (u — скасувати). Кадр із позначкою ✨ — найкращий за оцінкою алгоритму; але довіряйте власному оку.",
  help_pass2_title: "Прохід 2 · Групування (Сцена)",
  help_pass2_body:
    "Перемкніться на «Сцену», щоб побачити обране, перегруповане за місцем і образом, без огляду на час — зручно для галереї чи набору в Instagram. Видалені фото не показуються.",
  help_pass3_title: "Прохід 3 · Розкладка (Стрічка)",
  help_pass3_body:
    "«Стрічка» розкладає ваші ★ обрані у збалансовану сітку — чергування планів, сцени рознесені — щоб побачити, як набір виглядає разом.",
  help_download:
    "Коли все готово, «Завантажити обране» збереже обране й позначене «під питанням» як ZIP з недоторканими оригіналами. Нічого не змінюється, не переміщується й не вивантажується в інтернет.",
  help_got_it: "Зрозуміло",

  new_session: "Нова сесія",
  rename_session: "Перейменувати сесію",
  session_name: "Назва сесії",
  sub_bursts: "серій: {n}",
  sub_scenes: "сцен: {n}",
  sub_feed: "у стрічці: {n}",
  aria_grouping_mode: "Режим групування",
  aria_language: "Мова",
  mode_burst: "Серія",
  mode_scene: "Сцена",
  mode_feed: "Стрічка",
  mode_burst_title:
    "Серія — майже однакові кадри, зняті поспіль. Перший прохід відбору: оберіть найкращий кадр у кожній серії.",
  mode_scene_title:
    "Сцена — усі схожі кадри (те саме місце й образ) згруповані разом, без огляду на час. Другий прохід: зберіть галерею / набір для Instagram із обраного.",
  mode_feed_title:
    "Стрічка — ваше обране, розкладене у збалансовану сітку галереї/Instagram: чергування планів, сцени рознесені. Фінальний прохід: подивіться, як набір читається сіткою.",
  undecided: "без рішення: {n}",
  kept: "★ обрано: {n}",
  maybe_pill: "? під питанням: {n}",
  trash_pill: "🗑 видалено: {n}",
  hide_sorted: "Сховати розібрані",
  show_all: "Показати всі",
  hide_sorted_title: "Сховати вже розібрані фото (обрані, під питанням або видалені)",
  show_all_title: "Показати всі фото, зокрема вже розібрані",
  accept_picks: "✓ Прийняти підказки",
  accept_confirm: "Додати {n} підказок до обраного?",
  confirm: "Підтвердити",
  cancel: "Скасувати",
  accept_title: "Додати до обраного найкращий кадр алгоритму в кожній серії, де ще немає рішення",
  accept_none_title: "Немає підказок без рішення, які можна прийняти",
  download_picks: "⬇ Завантажити обране",
  download_disabled_title: "Спершу позначте кілька фото як обране або під питанням",
  download_title: "Завантажити ваше обране (обране + під питанням) як ZIP з оригіналами",

  // --- in-app updater (bottom of screen) ---
  version_label: "версія {v}",
  update_downloading: "Завантаження оновлення",
  update_ready: "Оновлення готове",
  update_relaunch_tip: "Перезапустити, щоб завершити оновлення",

  group: "Група",
  label_burst_pick: "{n} у серії — оберіть один кадр",
  label_single: "одиночний кадр",
  label_scene: "{n} у сцені",
  label_unique: "унікальний образ",
  close_call: "⚖ важко вирішити",
  close_call_title:
    "Два найкращі кадри відрізняються на крихту — алгоритм тут не впевнений. Довіртеся власному оку.",
  empty_hidden: "Немає чого показати. Спробуйте вимкнути «Сховати розібрані».",

  badge_suggested: "✨ підказка",
  badge_kept: "★ обрано",
  badge_maybe: "? під питанням",
  badge_trash: "🗑 видалено",
  btn_fav: "★ обрати",
  btn_maybe: "? під питанням",
  btn_trash: "🗑 видалити",
  btn_undo: "↩ скасувати",
  // icon-only labels for the dense per-card action row (locale-independent, equal width)
  btn_fav_short: "★",
  btn_maybe_short: "?",
  btn_trash_short: "🗑",
  btn_undo_short: "↩",
  mark_favorite: "Додати до обраного",
  remove_favorite: "Прибрати з обраного",
  mark_maybe: "Позначити «під питанням»",
  remove_maybe: "Прибрати «під питанням»",
  mark_trash: "Видалити",
  remove_trash: "Скасувати видалення",
  clear_label: "Скинути позначку",
  score: "оцінка {n}",
  bw: "ч/б",
  axes_title: "Осі",
  prev_group: "↑ попередня група",
  next_group: "наступна група ↓",
  prev_group_title: "Попередня група (↑)",
  next_group_title: "Наступна група (↓)",
  prev_photo_title: "Попереднє фото (←)",
  next_photo_title: "Наступне фото (→)",
  close_esc: "Закрити (Esc)",
  hover_zoom: "Наведіть, щоб збільшити — рухайте курсором, щоб роздивитися",
  suggested_caption: "✨ підказка",

  feed_planning: "Готуємо стрічку…",
  feed_failed: "Не вдалося скласти стрічку",
  feed_empty_pre: "Позначте кілька фото як ",
  feed_empty_strong: "★ обране",
  feed_empty_post: ", щоб скласти стрічку.",
  feed_hint:
    "{n} обраних розкладено у збалансовану сітку — чергування планів, сцени рознесені. Порядок читання — згори зліва.",

  status_label: "Статус",
  st_pending: "очікує",
  st_processing: "обробка",
  st_ready: "готово",
  st_err: "помилка",
  photos_pct: "{done} / {total} фото ({pct}%)",

  failed_load_session: "Не вдалося завантажити сесію",
  back_new_session: "← Нова сесія",
  analysis_failed: "Не вдалося проаналізувати",
  unknown_error: "Невідома помилка",
  loading: "Завантаження…",
  loading_groups: "Завантаження груп…",
  failed_load_groups: "Не вдалося завантажити групи",

  "reason:eyes open": "очі відкриті",
  "reason:all eyes open": "усі очі відкриті",
  "reason:sharp eyes": "різкі очі",
  "reason:smiling": "усмішка",
  "reason:everyone smiling": "усі усміхаються",
  "reason:eye contact": "погляд у камеру",
  "reason:well exposed": "гарна експозиція",
  "reason:catchlight": "відблиск в очах",
  "reason:sunglasses — judged on pose & expression": "окуляри — оцінка за позою та виразом",

  "cat:Focus": "Різкість",
  "cat:Subject": "Об’єкт",
  "cat:Compos": "Композ.",
  "cat:Expo": "Експоз.",
  "cat:Aesth": "Естет.",

  "axis:eye sharpness": "різкість очей",
  "axis:face sharpness": "різкість обличчя",
  "axis:subject vs bg": "об’єкт і фон",
  "axis:exposure": "експозиція",
  "axis:contrast": "контраст",
  "axis:eyes open": "очі відкриті",
  "axis:expression": "вираз обличчя",
  "axis:eye contact": "погляд у камеру",
  "axis:rule of thirds": "правило третин",
  "axis:headroom": "простір над головою",
  "axis:framing/size": "кадрування/розмір",
  "axis:clean bg": "чистий фон",
  "axis:aesthetic": "естетика",

  "scale:close": "крупний",
  "scale:medium": "середній",
  "scale:wide": "загальний",
};

const ru: Dict = {
  app_title: "Photo Cherrypick",
  home_tagline:
    "Выберите папку с фото (RAW или JPEG) для анализа и отбора. Всё остаётся на вашем компьютере — ничего не загружается в интернет.",
  choose_folder: "Выбрать папку…",
  analyze_folder: "Анализировать папку",
  choose_folder_title: "Обзор папок с фото на вашем компьютере",
  analyze_folder_title: "Проанализировать папку и начать отбор — ничто не покидает ваш компьютер",
  analyzing: "Анализ…",
  failed_create: "Не удалось создать сессию",
  recent_sessions: "Недавние сессии",
  n_photos: "{n} фото",
  status_analyzing: "анализ {done}/{total}…",
  status_queued: "в очереди…",
  status_error: "ошибка",
  status_kept_maybe: "{fav} выбрано · {maybe} под вопросом",
  delete_session: "Удалить сессию",
  delete_confirm:
    "Удалить «{name}»? Это удалит сессию и её решения по отбору (ваши файлы фото не затрагиваются).",
  close: "Закрыть",

  // --- how-to guide ---
  help_button: "Как пользоваться",
  help_title: "Как пользоваться Photo Cherrypick",
  help_loading_hint:
    "Пока фото анализируются, вот как устроен процесс — ваши решения сохраняются автоматически.",
  help_intro:
    "Проанализируйте папку один раз; все три прохода ниже работают с тем же набором фото. Ваши отметки ★ выбрать / ? под вопросом / 🗑 удалить сохраняются и переходят между всеми проходами — повторно загружать не нужно.",
  help_pass1_title: "Проход 1 · Отбор (Серия)",
  help_pass1_body:
    "Каждая группа — это серия почти одинаковых кадров. Выберите лучший: ★ выбрать, ? под вопросом, 🗑 удалить — клавиши f / m / x (u — отменить). Кадр с отметкой ✨ — лучший по оценке алгоритма; но доверяйте собственному глазу.",
  help_pass2_title: "Проход 2 · Группировка (Сцена)",
  help_pass2_body:
    "Переключитесь на «Сцену», чтобы увидеть выбранное, перегруппированное по месту и образу, без учёта времени — удобно для галереи или набора в Instagram. Удалённые фото не показываются.",
  help_pass3_title: "Проход 3 · Раскладка (Лента)",
  help_pass3_body:
    "«Лента» раскладывает ваши ★ выбранные в сбалансированную сетку — чередование планов, сцены разнесены — чтобы увидеть, как набор смотрится вместе.",
  help_download:
    "Когда всё готово, «Скачать выбранное» сохранит выбранное и отмеченное «под вопросом» как ZIP с нетронутыми оригиналами. Ничего не изменяется, не перемещается и не загружается в интернет.",
  help_got_it: "Понятно",

  new_session: "Новая сессия",
  rename_session: "Переименовать сессию",
  session_name: "Название сессии",
  sub_bursts: "серий: {n}",
  sub_scenes: "сцен: {n}",
  sub_feed: "в ленте: {n}",
  aria_grouping_mode: "Режим группировки",
  aria_language: "Язык",
  mode_burst: "Серия",
  mode_scene: "Сцена",
  mode_feed: "Лента",
  mode_burst_title:
    "Серия — почти одинаковые кадры, снятые подряд. Первый проход отбора: выберите лучший кадр в каждой серии.",
  mode_scene_title:
    "Сцена — все похожие кадры (то же место и образ) сгруппированы вместе, без учёта времени. Второй проход: соберите галерею / набор для Instagram из выбранного.",
  mode_feed_title:
    "Лента — ваше выбранное, разложенное в сбалансированную сетку галереи/Instagram: чередование планов, сцены разнесены. Финальный проход: посмотрите, как набор читается сеткой.",
  undecided: "без решения: {n}",
  kept: "★ выбрано: {n}",
  maybe_pill: "? под вопросом: {n}",
  trash_pill: "🗑 удалено: {n}",
  hide_sorted: "Скрыть разобранные",
  show_all: "Показать все",
  hide_sorted_title: "Скрыть уже разобранные фото (выбранные, под вопросом или удалённые)",
  show_all_title: "Показать все фото, включая уже разобранные",
  accept_picks: "✓ Принять подсказки",
  accept_confirm: "Добавить {n} подсказок в выбранное?",
  confirm: "Подтвердить",
  cancel: "Отмена",
  accept_title: "Добавить в выбранное лучший кадр алгоритма в каждой серии, где ещё нет решения",
  accept_none_title: "Нет подсказок без решения, которые можно принять",
  download_picks: "⬇ Скачать выбранное",
  download_disabled_title: "Сначала отметьте несколько фото как выбранное или под вопросом",
  download_title: "Скачать ваш выбор (выбранное + под вопросом) как ZIP с оригиналами",

  // --- in-app updater (bottom of screen) ---
  version_label: "версия {v}",
  update_downloading: "Загрузка обновления",
  update_ready: "Обновление готово",
  update_relaunch_tip: "Перезапустить, чтобы завершить обновление",

  group: "Группа",
  label_burst_pick: "{n} в серии — выберите один кадр",
  label_single: "одиночный кадр",
  label_scene: "{n} в сцене",
  label_unique: "уникальный образ",
  close_call: "⚖ трудно решить",
  close_call_title:
    "Два лучших кадра отличаются на волосок — алгоритм здесь не уверен. Доверьтесь собственному глазу.",
  empty_hidden: "Нечего показать. Попробуйте выключить «Скрыть разобранные».",

  badge_suggested: "✨ подсказка",
  badge_kept: "★ выбрано",
  badge_maybe: "? под вопросом",
  badge_trash: "🗑 удалено",
  btn_fav: "★ выбрать",
  btn_maybe: "? под вопросом",
  btn_trash: "🗑 удалить",
  btn_undo: "↩ отменить",
  // icon-only labels for the dense per-card action row (locale-independent, equal width)
  btn_fav_short: "★",
  btn_maybe_short: "?",
  btn_trash_short: "🗑",
  btn_undo_short: "↩",
  mark_favorite: "Добавить в выбранное",
  remove_favorite: "Убрать из выбранного",
  mark_maybe: "Отметить «под вопросом»",
  remove_maybe: "Убрать «под вопросом»",
  mark_trash: "Удалить",
  remove_trash: "Отменить удаление",
  clear_label: "Сбросить отметку",
  score: "оценка {n}",
  bw: "ч/б",
  axes_title: "Оси",
  prev_group: "↑ предыдущая группа",
  next_group: "следующая группа ↓",
  prev_group_title: "Предыдущая группа (↑)",
  next_group_title: "Следующая группа (↓)",
  prev_photo_title: "Предыдущее фото (←)",
  next_photo_title: "Следующее фото (→)",
  close_esc: "Закрыть (Esc)",
  hover_zoom: "Наведите, чтобы увеличить — двигайте курсором, чтобы рассмотреть",
  suggested_caption: "✨ подсказка",

  feed_planning: "Готовим ленту…",
  feed_failed: "Не удалось составить ленту",
  feed_empty_pre: "Отметьте несколько фото как ",
  feed_empty_strong: "★ выбранное",
  feed_empty_post: ", чтобы составить ленту.",
  feed_hint:
    "{n} выбранных разложено в сбалансированную сетку — чередование планов, сцены разнесены. Порядок чтения — сверху слева.",

  status_label: "Статус",
  st_pending: "ожидает",
  st_processing: "обработка",
  st_ready: "готово",
  st_err: "ошибка",
  photos_pct: "{done} / {total} фото ({pct}%)",

  failed_load_session: "Не удалось загрузить сессию",
  back_new_session: "← Новая сессия",
  analysis_failed: "Не удалось проанализировать",
  unknown_error: "Неизвестная ошибка",
  loading: "Загрузка…",
  loading_groups: "Загрузка групп…",
  failed_load_groups: "Не удалось загрузить группы",

  "reason:eyes open": "глаза открыты",
  "reason:all eyes open": "все глаза открыты",
  "reason:sharp eyes": "резкие глаза",
  "reason:smiling": "улыбка",
  "reason:everyone smiling": "все улыбаются",
  "reason:eye contact": "взгляд в камеру",
  "reason:well exposed": "хорошая экспозиция",
  "reason:catchlight": "блик в глазах",
  "reason:sunglasses — judged on pose & expression": "очки — оценка по позе и выражению",

  "cat:Focus": "Резкость",
  "cat:Subject": "Объект",
  "cat:Compos": "Композ.",
  "cat:Expo": "Экспоз.",
  "cat:Aesth": "Эстет.",

  "axis:eye sharpness": "резкость глаз",
  "axis:face sharpness": "резкость лица",
  "axis:subject vs bg": "объект и фон",
  "axis:exposure": "экспозиция",
  "axis:contrast": "контраст",
  "axis:eyes open": "глаза открыты",
  "axis:expression": "выражение лица",
  "axis:eye contact": "взгляд в камеру",
  "axis:rule of thirds": "правило третей",
  "axis:headroom": "пространство над головой",
  "axis:framing/size": "кадрирование/размер",
  "axis:clean bg": "чистый фон",
  "axis:aesthetic": "эстетика",

  "scale:close": "крупный",
  "scale:medium": "средний",
  "scale:wide": "общий",
};

const DICTS: Record<Lang, Dict> = { en, uk, ru };

function interpolate(s: string, vars?: Record<string, string | number>): string {
  if (!vars) return s;
  let out = s;
  for (const [k, v] of Object.entries(vars)) out = out.replace(`{${k}}`, String(v));
  return out;
}

// Every language's rendering of a key (same fallback chain as `t`). Used to reserve the width of the
// widest translation so a control's size doesn't change when the language switches — see StableLabel.
export function tVariants(key: string, vars?: Record<string, string | number>): string[] {
  return (Object.keys(DICTS) as Lang[]).map((l) =>
    interpolate(DICTS[l][key] ?? en[key] ?? key, vars),
  );
}

interface I18n {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const Ctx = createContext<I18n | null>(null);

function detectInitial(): Lang {
  try {
    const saved = localStorage.getItem("lang");
    if (saved === "en" || saved === "uk" || saved === "ru") return saved;
    const nav = navigator.language?.toLowerCase() ?? "";
    if (nav.startsWith("uk")) return "uk";
    if (nav.startsWith("ru")) return "ru";
  } catch {
    // ignore (no localStorage)
  }
  return "en";
}

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectInitial);
  const setLang = useCallback((l: Lang) => {
    try {
      localStorage.setItem("lang", l);
    } catch {
      // ignore
    }
    setLangState(l);
  }, []);
  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) =>
      interpolate(DICTS[lang][key] ?? en[key] ?? key, vars),
    [lang],
  );
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useI18n must be used within <LangProvider>");
  return ctx;
}
