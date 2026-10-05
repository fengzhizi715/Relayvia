import { create } from "zustand";

import { en, type TranslationKey } from "./en";
import { zh } from "./zh";

export type { TranslationKey } from "./en";

export type Language = "en" | "zh";

export type TranslationParams = Record<string, string | number>;

export type Translator = (key: TranslationKey, params?: TranslationParams) => string;

export const LANGUAGES: Array<{ id: Language; label: string }> = [
  { id: "en", label: "EN" },
  { id: "zh", label: "中文" },
];

export const LOCALES: Record<Language, string> = { en: "en-US", zh: "zh-CN" };

const STORAGE_KEY = "relayvia.language";

const dictionaries: Record<Language, Record<TranslationKey, string>> = { en, zh };

function readInitialLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "zh") return stored;
  } catch {
    return "en";
  }
  return "en";
}

type I18nStore = {
  language: Language;
  setLanguage: (language: Language) => void;
};

export const useI18nStore = create<I18nStore>((set) => ({
  language: readInitialLanguage(),
  setLanguage: (language) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, language);
    } catch {
      set({ language });
      return;
    }
    set({ language });
  },
}));

export function getLanguage(): Language {
  return useI18nStore.getState().language;
}

function interpolate(template: string, params?: TranslationParams): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match,
  );
}

export function translate(language: Language, key: TranslationKey, params?: TranslationParams): string {
  const template = dictionaries[language][key] ?? en[key] ?? key;
  return interpolate(template, params);
}

export function t(key: TranslationKey, params?: TranslationParams): string {
  return translate(getLanguage(), key, params);
}

export function translateStatus(language: Language, status: string): string {
  const key = `status.${status.toLowerCase()}` as TranslationKey;
  if (Object.prototype.hasOwnProperty.call(en, key)) return translate(language, key);
  return status.replaceAll("_", " ").toUpperCase();
}

export function useTranslation(): {
  language: Language;
  locale: string;
  setLanguage: (language: Language) => void;
  t: Translator;
  tStatus: (status: string) => string;
} {
  const language = useI18nStore((state) => state.language);
  const setLanguage = useI18nStore((state) => state.setLanguage);
  return {
    language,
    locale: LOCALES[language],
    setLanguage,
    t: (key, params) => translate(language, key, params),
    tStatus: (status) => translateStatus(language, status),
  };
}
