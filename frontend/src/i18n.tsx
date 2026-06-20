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

export type Lang = "en" | "uk";

type Dict = Record<string, string>;

const en: Dict = {
  // --- home / session input ---
  app_title: "Photo Cherrypick",
  home_tagline:
    "Pick a folder of photos (RAW or JPEG) to analyze and cull. Everything stays on your computer — nothing is uploaded.",
  choose_folder: "Choose folder…",
  analyze_folder: "Analyze folder",
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
  maybe_pill: "{n} maybe",
  trash_pill: "🗑 {n} trash",
  hide_sorted: "Hide sorted",
  show_all: "Show all",
  accept_picks: "✓ Accept picks",
  accept_confirm: "Favorite {n} suggested picks?",
  confirm: "Confirm",
  cancel: "Cancel",
  accept_title: "Favorite the algorithm's best-of-burst pick in every group still undecided",
  accept_none_title: "No undecided suggestions left to accept",
  download_picks: "⬇ Download picks",
  download_disabled_title: "Mark some photos favorite or maybe first",
  download_title: "Download your picks (favorites + maybe) as a ZIP of the original files",

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
  badge_suggested: "suggested",
  badge_kept: "★ kept",
  badge_maybe: "maybe",
  badge_trash: "🗑 trash",
  btn_fav: "★ fav",
  btn_maybe: "maybe",
  btn_trash_short: "🗑",
  btn_trash: "🗑 trash",
  btn_undo: "↩ undo",
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
  prev_group: "‹ prev group",
  next_group: "next group ›",
  prev_group_title: "Previous group (↑)",
  next_group_title: "Next group (↓)",
  prev_photo_title: "Previous photo (←)",
  next_photo_title: "Next photo (→)",
  close_esc: "Close (Esc)",
  hover_zoom: "Hover to zoom — move the cursor to look around",
  suggested_caption: "★ suggested",

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
  analyzing: "Аналіз…",
  failed_create: "Не вдалося створити сесію",
  recent_sessions: "Останні сесії",
  n_photos: "{n} фото",
  status_analyzing: "аналіз {done}/{total}…",
  status_queued: "у черзі…",
  status_error: "помилка",
  status_kept_maybe: "{fav} обрано · {maybe} можливо",
  delete_session: "Видалити сесію",
  delete_confirm:
    "Видалити «{name}»? Це прибере сесію та її рішення щодо відбору (ваші файли фото не зачіпаються).",

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
  maybe_pill: "можливо: {n}",
  trash_pill: "🗑 кошик: {n}",
  hide_sorted: "Сховати оброблені",
  show_all: "Показати всі",
  accept_picks: "✓ Прийняти підказки",
  accept_confirm: "Додати {n} підказок до обраного?",
  confirm: "Підтвердити",
  cancel: "Скасувати",
  accept_title: "Додати до обраного найкращий кадр алгоритму в кожній серії, де ще немає рішення",
  accept_none_title: "Немає підказок без рішення, які можна прийняти",
  download_picks: "⬇ Завантажити обране",
  download_disabled_title: "Спершу позначте кілька фото як обране або можливо",
  download_title: "Завантажити ваше обране (обране + можливо) як ZIP з оригіналами",

  group: "Група",
  label_burst_pick: "{n} у серії — оберіть один",
  label_single: "одиночний кадр",
  label_scene: "{n} у сцені",
  label_unique: "унікальний образ",
  close_call: "⚖ важко вирішити",
  close_call_title:
    "Два найкращі кадри відрізняються на крихту — алгоритм тут не впевнений. Довіртеся власному оку.",
  empty_hidden: "Немає чого показати. Спробуйте вимкнути «Сховати оброблені».",

  badge_suggested: "підказка",
  badge_kept: "★ обрано",
  badge_maybe: "можливо",
  badge_trash: "🗑 кошик",
  btn_fav: "★ обрати",
  btn_maybe: "можливо",
  btn_trash_short: "🗑",
  btn_trash: "🗑 кошик",
  btn_undo: "↩ скасувати",
  mark_favorite: "Додати до обраного",
  remove_favorite: "Прибрати з обраного",
  mark_maybe: "Позначити «можливо»",
  remove_maybe: "Прибрати «можливо»",
  mark_trash: "До кошика",
  remove_trash: "Прибрати з кошика",
  clear_label: "Скинути позначку",
  score: "оцінка {n}",
  bw: "ч/б",
  axes_title: "Осі",
  prev_group: "‹ попередня група",
  next_group: "наступна група ›",
  prev_group_title: "Попередня група (↑)",
  next_group_title: "Наступна група (↓)",
  prev_photo_title: "Попереднє фото (←)",
  next_photo_title: "Наступне фото (→)",
  close_esc: "Закрити (Esc)",
  hover_zoom: "Наведіть, щоб збільшити — рухайте курсор, щоб роздивитися",
  suggested_caption: "★ підказка",

  feed_planning: "Готуємо стрічку…",
  feed_failed: "Не вдалося скласти стрічку",
  feed_empty_pre: "Позначте кілька фото як ",
  feed_empty_strong: "★ обране",
  feed_empty_post: ", щоб скласти стрічку.",
  feed_hint:
    "{n} обраних розкладено у збалансовану сітку — чергування планів, сцени рознесені. Порядок читання — зверху-зліва.",

  status_label: "Статус",
  st_pending: "очікує",
  st_processing: "обробка",
  st_ready: "готово",
  st_err: "помилка",
  photos_pct: "{done} / {total} фото ({pct}%)",

  failed_load_session: "Не вдалося завантажити сесію",
  back_new_session: "← Нова сесія",
  analysis_failed: "Аналіз не вдався",
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

const DICTS: Record<Lang, Dict> = { en, uk };

function interpolate(s: string, vars?: Record<string, string | number>): string {
  if (!vars) return s;
  let out = s;
  for (const [k, v] of Object.entries(vars)) out = out.replace(`{${k}}`, String(v));
  return out;
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
    if (saved === "en" || saved === "uk") return saved;
    if (navigator.language?.toLowerCase().startsWith("uk")) return "uk";
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
