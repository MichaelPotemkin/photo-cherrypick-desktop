import { useI18n, type Lang } from "../i18n";

// Two-segment EN / УК language switch (persisted in localStorage by the i18n provider).
const LANGS: { code: Lang; label: string }[] = [
  { code: "en", label: "EN" },
  { code: "uk", label: "УК" },
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
          onClick={() => setLang(l.code)}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
