import { useI18n, type Lang } from "../i18n";

// EN / УК / РУ language switch (persisted in localStorage by the i18n provider).
// `name` is the endonym shown in the hover tooltip (kept in its own language by convention).
const LANGS: { code: Lang; label: string; name: string }[] = [
  { code: "en", label: "EN", name: "English" },
  { code: "uk", label: "УК", name: "Українська" },
  { code: "ru", label: "РУ", name: "Русский" },
];

export default function LangToggle() {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="lang-toggle" role="group" aria-label={t("aria_language")}>
      {LANGS.map((l) => (
        <button
          key={l.code}
          type="button"
          className={`lang-btn${lang === l.code ? " active" : ""}`}
          aria-pressed={lang === l.code}
          // visible label kept inside the accessible name (WCAG 2.5.3 Label in Name) while still
          // exposing the friendlier endonym, e.g. "EN — English" / "УК — Українська"
          aria-label={`${l.label} — ${l.name}`}
          data-tip={l.name}
          onClick={() => setLang(l.code)}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
