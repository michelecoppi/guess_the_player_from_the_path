/**
 * Pure string and formatting utilities.
 * Exactly mirrors and types the legacy webapp/client.js functions.
 */

export function escapeHtml(value: unknown): string {
  return String(value == null ? "" : value).replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c] || c
  );
}

export function initials(name: string | null | undefined): string {
  return (
    (name || "?")
      .split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0].toUpperCase())
      .join("") || "?"
  );
}

export function weekNumber(week: string | null | undefined): string {
  return String(week || "").split("W")[1] || "";
}
