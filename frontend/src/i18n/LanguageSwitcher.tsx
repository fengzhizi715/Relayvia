import { LANGUAGES, useTranslation } from "./index";

export function LanguageSwitcher() {
  const { language, setLanguage, t } = useTranslation();

  return (
    <div className="language-switcher" role="group" aria-label={t("app.language")}>
      {LANGUAGES.map((item) => (
        <button
          className={item.id === language ? "language-switcher-item language-switcher-item--active" : "language-switcher-item"}
          key={item.id}
          type="button"
          onClick={() => setLanguage(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
