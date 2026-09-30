import { icon } from "@/components/Icon";
import { getLanguage, type SupportedLanguage } from "@/i18n";
import { escapeHtml } from "@/utils/format";
import type { EventCard } from "./types";

/**
 * Where a running event shows up outside the Events page (#248):
 *
 * - a banner at the top of the Daily, the screen the app opens on;
 * - a highlighted card at the top of the Arena hub;
 * - a dot on the Arena tab of the nav bar while today's event is still to be played.
 *
 * Everything is derived from the `EventCard`s of `/app/api/arena` (`mode: "events"`): no
 * extra endpoint, no extra field. Nothing is shown while the events are loading or when the
 * request failed - the banner is an invitation, never an error surface.
 */

/** Where the user opened the Events page from; sent with the load for `event_viewed`. */
export type EventEntry = "daily_banner" | "arena_card" | "arena_list";

const STRINGS: Record<SupportedLanguage, Record<string, string>> = {
  it: {
    kicker: "Evento in corso",
    lastDay: "Ultimo giorno",
    lastHours: "Finisce tra {h} h",
    daysLeft: "Ancora {n} giorni",
    points: "{n} pt oggi",
    bonus: "+1 al primo",
    podium: "🏆 podio",
    todo: "Da giocare oggi",
    solved: "Risolto oggi · +{n} pt",
    out: "Tentativi finiti per oggi",
    play: "Gioca",
    view: "Vedi",
    navDot: "evento da giocare",
  },
  en: {
    kicker: "Live event",
    lastDay: "Last day",
    lastHours: "Ends in {h} h",
    daysLeft: "{n} days left",
    points: "{n} pts today",
    bonus: "+1 first solver",
    podium: "🏆 podium",
    todo: "To play today",
    solved: "Solved today · +{n} pts",
    out: "No attempts left today",
    play: "Play",
    view: "View",
    navDot: "event to play",
  },
  es: {
    kicker: "Evento en curso",
    lastDay: "Último día",
    lastHours: "Termina en {h} h",
    daysLeft: "Quedan {n} días",
    points: "{n} pts hoy",
    bonus: "+1 al primero",
    podium: "🏆 podio",
    todo: "Por jugar hoy",
    solved: "Resuelto hoy · +{n} pts",
    out: "Sin intentos por hoy",
    play: "Jugar",
    view: "Ver",
    navDot: "evento por jugar",
  },
};

export function es(key: string, args: Record<string, string | number> = {}): string {
  const table = STRINGS[getLanguage()] ?? STRINGS.it;
  const text = table[key] ?? STRINGS.it[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name: string) => String(args[name] ?? ""));
}

/** True when today's round of the event can still be played. */
export function isPending(event: EventCard): boolean {
  return event.available && !event.progress.finished;
}

/** The event worth showing: one still to play today first, otherwise any playable one. */
export function spotlightEvent(events: readonly EventCard[] | null | undefined): EventCard | null {
  const playable = (events ?? []).filter((event) => event.available);
  return playable.find(isPending) ?? playable[0] ?? null;
}

export function hasPendingEvent(events: readonly EventCard[] | null | undefined): boolean {
  return (events ?? []).some(isPending);
}

/** Hours until midnight in Italy, where the game's days change (services/dates.py). */
export function hoursLeftToday(now: Date = new Date()): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Rome", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(now);
  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? 0);
  const minute = Number(parts.find((part) => part.type === "minute")?.value ?? 0);
  return Math.max(1, Math.ceil(24 - hour - minute / 60));
}

/** "Last day · ends in 5 h" or "3 days left", counting today. */
export function timeLeftLabel(event: EventCard, now: Date = new Date()): string {
  const days = (event.dates ?? []).filter((day) => day >= event.day).length;
  if (days <= 1) return `${es("lastDay")} · ${es("lastHours", { h: hoursLeftToday(now) })}`;
  return es("daysLeft", { n: days });
}

function statusLabel(event: EventCard): string {
  if (event.progress.solved) return es("solved", { n: event.progress.points });
  if (event.progress.finished) return es("out");
  return es("todo");
}

function prizes(event: EventCard): string {
  const items = [es("points", { n: event.points })];
  if (event.bonus_available && !event.progress.finished) items.push(es("bonus"));
  items.push(es("podium"));
  return items.map((item) => `<span>${escapeHtml(item)}</span>`).join("");
}

/**
 * The banner (Daily) or the card (Arena hub). A single button: the whole surface opens the
 * event, so the target stays large on a phone and there is one tab stop.
 */
export function renderEventSpotlight(
  event: EventCard | null,
  entry: EventEntry,
  now: Date = new Date(),
): string {
  if (!event) return "";
  const pending = isPending(event);
  const label = `${es("kicker")}: ${event.name}. ${timeLeftLabel(event, now)}. ${statusLabel(event)}.`;
  return `<button type="button" class="event-spotlight ${pending ? "is-pending" : "is-done"}" data-event-open="${escapeHtml(event.code)}" data-event-entry="${entry}" aria-label="${escapeHtml(label)}">
    <span class="event-spotlight-icon" aria-hidden="true">${icon("events")}</span>
    <span class="event-spotlight-body">
      <span class="event-spotlight-top"><span class="event-spotlight-kicker">${pending ? '<i class="live-dot"></i>' : ""}${escapeHtml(es("kicker"))}</span><span class="event-spotlight-time">${escapeHtml(timeLeftLabel(event, now))}</span></span>
      <b class="event-spotlight-name">${escapeHtml(event.name)}</b>
      <span class="event-spotlight-prizes">${prizes(event)}</span>
      <span class="event-spotlight-status">${pending ? "" : icon(event.progress.solved ? "check" : "close")}${escapeHtml(statusLabel(event))}</span>
    </span>
    <span class="event-spotlight-cta" aria-hidden="true">${escapeHtml(pending ? es("play") : es("view"))}${icon("arrow")}</span>
  </button>`;
}
