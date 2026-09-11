import type { SupportedLanguage } from "./types";
import { TRANSLATIONS } from "./translations";

export * from "./types";
export * from "./translations";

const SUPPORTED_LANGUAGES: SupportedLanguage[] = ["it", "es", "en"];
let currentLanguage: SupportedLanguage = "it";

/**
 * Resolves a language code to one of the supported languages ("it", "es", "en").
 * Exactly replicates the rule used by server and legacy webapp.
 */
export function resolveLanguage(code?: string | null): SupportedLanguage {
  if (!code) return "en";
  const short = String(code).toLowerCase().split("-")[0];
  return (SUPPORTED_LANGUAGES.includes(short as SupportedLanguage) ? short : "en") as SupportedLanguage;
}

export function setLanguage(lang: SupportedLanguage): void {
  if (SUPPORTED_LANGUAGES.includes(lang)) {
    currentLanguage = lang;
  }
}

export function getLanguage(): SupportedLanguage {
  return currentLanguage;
}

/**
 * Retrieves a translated string by dot notation path (e.g. "common.appName", "shell.activeTab")
 * and replaces placeholders like {name}, {tab}, {issue}.
 */
export function t(
  path: string,
  params?: Record<string, string | number>,
  lang?: SupportedLanguage
): string {
  const activeLang = lang || currentLanguage;
  const dict = TRANSLATIONS[activeLang] || TRANSLATIONS.en;

  const parts = path.split(".");
  let current: any = dict;
  for (const part of parts) {
    if (current && typeof current === "object" && part in current) {
      current = current[part];
    } else {
      current = undefined;
      break;
    }
  }

  if (typeof current !== "string") {
    return path;
  }

  if (!params) return current;

  return current.replace(/\{(\w+)\}/g, (_, key) => {
    return key in params ? String(params[key]) : `{${key}}`;
  });
}
