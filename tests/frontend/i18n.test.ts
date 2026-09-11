import { test } from "node:test";
import assert from "node:assert/strict";
import {
  resolveLanguage,
  setLanguage,
  getLanguage,
  t,
  TRANSLATIONS,
} from "../../webapp/src/i18n";

test("resolveLanguage normalizes language codes to supported values", () => {
  assert.equal(resolveLanguage("it"), "it");
  assert.equal(resolveLanguage("it-IT"), "it");
  assert.equal(resolveLanguage("es-MX"), "es");
  assert.equal(resolveLanguage("pt-BR"), "en");
  assert.equal(resolveLanguage(null), "en");
  assert.equal(resolveLanguage(undefined), "en");
  assert.equal(resolveLanguage(""), "en");
});

test("t() retrieves translation with fallback and interpolation", () => {
  setLanguage("it");
  assert.equal(getLanguage(), "it");
  assert.equal(t("common.appName"), "Guess the Player");
  assert.equal(
    t("shell.activeTab", { tab: "play" }),
    "Scheda attiva: play"
  );
  assert.equal(
    t("migration.badge", { issue: 40 }),
    "In arrivo in #40"
  );
  assert.equal(t("non.existent.key"), "non.existent.key");
});

test("all supported languages (it, en, es) have identical translation structure", () => {
  function getKeys(obj: Record<string, any>, prefix = ""): string[] {
    const keys: string[] = [];
    for (const [k, v] of Object.entries(obj)) {
      const full = prefix ? `${prefix}.${k}` : k;
      if (v && typeof v === "object" && !Array.isArray(v)) {
        keys.push(...getKeys(v, full));
      } else {
        keys.push(full);
      }
    }
    return keys.sort();
  }

  const itKeys = getKeys(TRANSLATIONS.it);
  assert.ok(itKeys.length > 0);

  for (const lang of ["en", "es"] as const) {
    const langKeys = getKeys(TRANSLATIONS[lang]);
    assert.deepStrictEqual(langKeys, itKeys, `Mismatch in translation keys for ${lang}`);
  }
});
