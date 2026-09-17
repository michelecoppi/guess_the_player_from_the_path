import { getLanguage } from "@/i18n";

/**
 * The two legal pages (webapp/terms.html, webapp/privacy.html) served by the bot itself.
 * They must stay reachable from anywhere in the Mini App, not only from the Shop.
 */
export function legalHref(page: "terms" | "privacy", anchor?: string): string {
  return `/${page}?lang=${encodeURIComponent(getLanguage())}${anchor ? `#${anchor}` : ""}`;
}
