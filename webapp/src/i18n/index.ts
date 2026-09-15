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

function resolvePath(path: string, lang?: SupportedLanguage): unknown {
  const activeLang = lang || currentLanguage;
  const dict = TRANSLATIONS[activeLang] || TRANSLATIONS.en;

  const parts = path.split(".");
  let current: unknown = dict;
  for (const part of parts) {
    if (current && typeof current === "object" && part in current) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return current;
}

function interpolate(template: string, params: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key) => {
    return key in params ? String(params[key]) : `{${key}}`;
  });
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
  const current = resolvePath(path, lang);

  if (typeof current !== "string") {
    return path;
  }

  if (!params) return current;

  return interpolate(current, params);
}

/**
 * Retrieves a pluralized, count-aware translated string. `path` must point to a
 * `{ one, other }` pair (see `PluralForms`): the CLDR-style rule used here — "one"
 * exactly for a count of 1, "other" for everything else, including 0 — matches how
 * Italian, English and Spanish singularize/pluralize countable nouns. `{n}` in the
 * chosen form is replaced with `count`.
 */
export function tCount(path: string, count: number, lang?: SupportedLanguage): string {
  const current = resolvePath(path, lang);

  if (!current || typeof current !== "object") {
    return path;
  }

  const forms = current as Partial<Record<"one" | "other", string>>;
  const form = count === 1 ? forms.one : forms.other;

  if (typeof form !== "string") {
    return path;
  }

  return interpolate(form, { n: count });
}
