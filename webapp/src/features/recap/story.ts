import { icon, type IconName } from "@/components/Icon";
import { getTelegramWebApp } from "@/telegram/webapp";
import { escapeHtml } from "@/utils/format";
import { prepareRecapShare } from "./api";
import { monthName, rs } from "./strings";
import type { MonthlyRecap, RecapLook } from "./types";

/**
 * The animated monthly recap (#245): a full-screen story, one slide per interesting number.
 *
 * It is an overlay appended to <body>, not a page of the router: it opens from the Daily
 * banner or from the Profile, and closing it leaves the page underneath exactly as it was.
 * Slides without data (no gem, no lucky club, no saved closure) are simply not built.
 */

interface Slide {
  tone: string;
  html: string;
  duration: number;
  enter?: (el: HTMLElement) => void;
}

const HOLD_TO_PAUSE_MS = 180;

function reducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function countUp(el: HTMLElement): void {
  const target = Number(el.dataset.count || 0);
  if (reducedMotion()) {
    el.textContent = String(target);
    return;
  }
  const start = performance.now();
  const step = (now: number) => {
    const progress = Math.min(1, (now - start) / 1100);
    el.textContent = String(Math.round(target * (1 - Math.pow(1 - progress, 3))));
    if (progress < 1) requestAnimationFrame(step);
  };
  el.textContent = "0";
  setTimeout(() => requestAnimationFrame(step), 250);
}

function years(stop: { start_year?: number; end_year?: number | null }): string {
  if (!stop.start_year) return "";
  return stop.end_year && stop.end_year !== stop.start_year ? `${stop.start_year} – ${stop.end_year}` : `${stop.start_year}`;
}

const HEX = /^#[0-9a-f]{6}$/i;

/** The final card wears the equipped card cosmetic: only validated colours reach the style. */
function cardStyle(look?: RecapLook): string {
  const card = look?.card || {};
  const vars: string[] = [];
  if (card.paper && HEX.test(card.paper)) vars.push(`--recap-paper:${card.paper}`);
  if (card.ink && HEX.test(card.ink)) vars.push(`--recap-ink:${card.ink}`);
  if (card.glow && HEX.test(card.glow)) vars.push(`--recap-glow:${card.glow}`);
  return vars.join(";");
}

export function buildSlides(recap: MonthlyRecap, name: string, look?: RecapLook): Slide[] {
  const month = monthName(recap.month);
  const solved = recap.solved ?? 0;
  const days = recap.days ?? 30;
  const slides: Slide[] = [];

  slides.push({
    tone: "pitch",
    duration: 3400,
    html: `<div class="recap-center">
      <div class="recap-ball a" aria-hidden="true">${icon("career")}</div>
      <p class="recap-kicker a" style="--d:.25s">${escapeHtml(rs("introKicker", { name: name || "?" }))}</p>
      <h2 class="recap-display recap-huge a" style="--d:.45s">${escapeHtml(month)}</h2>
      <p class="recap-muted a" style="--d:.75s">${escapeHtml(rs("introSub"))}</p>
    </div>`,
  });

  const cells = (recap.calendar || [])
    .map((status, index) => `<i class="recap-cell ${status}" style="--d:${(0.35 + index * 0.035).toFixed(2)}s"></i>`)
    .join("");
  slides.push({
    tone: "night",
    duration: 4400,
    html: `<p class="recap-kicker a">${escapeHtml(rs("playedKicker"))}</p>
      <p class="recap-display recap-big a" style="--d:.1s"><span class="accent" data-count="${recap.played}">${recap.played}</span><small> ${escapeHtml(rs("playedOf", { days }))}</small></p>
      <p class="a" style="--d:.2s">${escapeHtml(rs("playedSub", { month }))}</p>
      <div class="recap-calendar" aria-hidden="true">${cells}</div>
      <p class="recap-legend a" style="--d:1.4s"><span class="won">${escapeHtml(rs("won"))}</span><span class="lost">${escapeHtml(rs("lost"))}</span><span class="skip">${escapeHtml(rs("skip"))}</span></p>`,
  });

  const attempts = recap.attempts || [0, 0, 0];
  const most = Math.max(1, ...attempts);
  slides.push({
    tone: "slate",
    duration: 4600,
    html: `<p class="recap-kicker a">${escapeHtml(rs("solvedKicker"))}</p>
      <p class="recap-display recap-giant a" style="--d:.1s" data-count="${solved}">${solved}</p>
      <p class="recap-muted a" style="--d:.2s">${escapeHtml(rs("solvedSub"))}</p>
      <div class="recap-bars-chart">${attempts.map((count, index) => `
        <div class="a" style="--d:${(0.35 + index * 0.15).toFixed(2)}s">
          <div class="recap-bar-label"><span>${escapeHtml(rs("attempt", { n: index + 1 }))}</span><b>${count}</b></div>
          <div class="recap-bar"><i class="t${index}" style="--w:${Math.round((count / most) * 100)}%;--d:${(0.5 + index * 0.2).toFixed(2)}s"></i></div>
        </div>`).join("")}</div>`,
  });

  if ((recap.best_streak ?? 0) >= 2) {
    slides.push({
      tone: "amber",
      duration: 3600,
      html: `<div class="recap-center">
        <span class="recap-flame a pop" aria-hidden="true">${icon("flame")}</span>
        <p class="recap-display recap-giant warm a" style="--d:.3s" data-count="${recap.best_streak}">${recap.best_streak}</p>
        <p class="recap-display recap-title a" style="--d:.45s">${escapeHtml(rs("streakTitle"))}</p>
        <p class="recap-muted a" style="--d:.8s">${escapeHtml(rs("streakSub"))}</p>
      </div>`,
    });
  }

  if (recap.gem) {
    const gem = recap.gem;
    // A long career does not fit a phone screen: the start and the end tell the story.
    const shown: ({ team: string; start_year?: number; end_year?: number | null } | null)[] =
      gem.path.length > 7 ? [...gem.path.slice(0, 4), null, ...gem.path.slice(-2)] : gem.path;
    const stops = shown
      .map((stop, index) => stop
        ? `<li class="a" style="--d:${(0.55 + index * 0.35).toFixed(2)}s"><b>${escapeHtml(stop.team)}</b><span>${escapeHtml(years(stop))}</span></li>`
        : `<li class="a recap-path-gap" style="--d:${(0.55 + index * 0.35).toFixed(2)}s"><b>…</b></li>`)
      .join("");
    slides.push({
      tone: "night",
      duration: 3200 + shown.length * 350 + 1600,
      html: `<p class="recap-kicker warm a">${escapeHtml(rs("gemKicker"))}</p>
        <p class="recap-display recap-title a" style="--d:.1s">${escapeHtml(rs("gemTitle", { rate: gem.rate }))}</p>
        ${gem.attempts ? `<p class="recap-muted a" style="--d:.2s">${escapeHtml(rs("gemSub", { attempts: gem.attempts }))}</p>` : ""}
        <ol class="recap-path">${stops}</ol>
        <p class="recap-display recap-reveal a pop" style="--d:${(0.8 + shown.length * 0.35).toFixed(2)}s">${escapeHtml(gem.name)}</p>`,
    });
  }

  if (recap.lucky_club) {
    const club = recap.lucky_club;
    const initials = club.team.replace(/[^A-Za-zÀ-ÿ ]/g, "").split(/\s+/).filter(Boolean)
      .map((word) => word[0]).join("").slice(0, 3).toUpperCase() || club.team.slice(0, 3).toUpperCase();
    slides.push({
      tone: "card",
      duration: 4400,
      html: `<div class="recap-center">
        <p class="recap-kicker a">${escapeHtml(rs("clubKicker"))}</p>
        <div class="recap-crest a pop" style="--d:.15s"><span class="recap-display">${escapeHtml(initials)}</span></div>
        <p class="recap-display recap-title a" style="--d:.35s">${escapeHtml(club.team)}</p>
        <p class="a" style="--d:.5s">${escapeHtml(rs("clubSub", { count: club.count, solved }))}</p>
        <p class="recap-chips a" style="--d:.8s">${club.players.map((player) => `<span>${escapeHtml(player)}</span>`).join("")}${club.count > club.players.length ? `<span>+${club.count - club.players.length}</span>` : ""}</p>
      </div>`,
    });
  }

  if (recap.style) {
    const key = recap.style.key;
    const glyphs: Record<string, IconName> = {
      professor: "star", sniper: "target", purist: "check", last_minute: "clock", marathon: "calendar", playmaker: "arena",
    };
    const glyph = glyphs[key] || "ranking";
    slides.push({
      tone: "pitch",
      duration: 4200,
      html: `<div class="recap-center">
        <p class="recap-kicker a">${escapeHtml(rs("styleKicker"))}</p>
        <div class="recap-style-card a flip" style="--d:.2s">
          <span class="recap-style-icon" aria-hidden="true">${icon(glyph)}</span>
          <p class="recap-display recap-title">${escapeHtml(rs(`style.${key}`))}</p>
          <p>${escapeHtml(rs(`styleSub.${key}`, { value: recap.style.value, days }))}</p>
        </div>
      </div>`,
    });
  }

  if (recap.better_than != null || (recap.firsts ?? 0) > 0) {
    slides.push({
      tone: "slate",
      duration: 4600,
      html: `<p class="recap-kicker a">${escapeHtml(rs("communityKicker"))}</p>
        ${recap.better_than != null ? `
          <p class="recap-display recap-title a" style="--d:.1s">${escapeHtml(rs("betterThan"))} <span class="accent"><span data-count="${recap.better_than}">${recap.better_than}</span>%</span></p>
          <p class="recap-muted a" style="--d:.15s">${escapeHtml(rs("betterThanSub"))}</p>
          <div class="recap-meter a" style="--d:.2s"><i style="--w:${recap.better_than}%"></i></div>` : ""}
        ${(recap.firsts ?? 0) > 0 ? `<div class="recap-row a" style="--d:.9s">${icon("bolt")}<div><b>${escapeHtml(rs("firsts", { n: recap.firsts! }))}</b><small>${escapeHtml(rs("firstsSub"))}</small></div></div>` : ""}`,
    });
  }

  const tiles: [string, string][] = [
    [`${solved}/${recap.played}`, rs("finalSolved")],
    [String(recap.best_streak ?? 0), rs("finalStreak")],
    recap.gem ? [`${recap.gem.rate}%`, rs("finalGem")] : [String(attempts[0]), rs("finalFirstTry")],
  ];
  if (recap.better_than != null) tiles.push([`TOP ${Math.max(1, 100 - recap.better_than)}%`, rs("finalRank")]);
  slides.push({
    tone: "night",
    duration: Number.POSITIVE_INFINITY,
    html: `<div class="recap-center">
      <div class="recap-final a pop" style="${cardStyle(look)}" data-finish="${escapeHtml(look?.card?.finish || "plain")}">
        <p class="recap-final-top">GUESS THE PLAYER</p>
        <p class="recap-final-month">${escapeHtml(month.toUpperCase())} ${escapeHtml(recap.month.slice(0, 4))}</p>
        <p class="recap-display recap-final-name">${look?.number ? `<small>${escapeHtml(look.number)}</small> ` : ""}${escapeHtml(name || "?")}</p>
        ${look?.title ? `<p class="recap-final-title">${escapeHtml(look.title)}</p>` : ""}
        <p class="recap-final-sub">${escapeHtml(recap.style ? rs(`style.${recap.style.key}`) : "")}${recap.lucky_club ? ` · ${escapeHtml(recap.lucky_club.team)}` : ""}</p>
        <div class="recap-final-grid">${tiles.map(([value, label]) => `<div><b class="recap-display">${escapeHtml(value)}</b><span>${escapeHtml(label)}</span></div>`).join("")}</div>
      </div>
      <button type="button" class="btn recap-share a" style="--d:.5s" data-recap-share>${icon("share")}${escapeHtml(rs("share"))}</button>
      <button type="button" class="btn ghost recap-again a" style="--d:.6s" data-recap-again>${escapeHtml(rs("again"))}</button>
      <p class="recap-toast" role="status" data-recap-toast></p>
    </div>`,
  });
  return slides;
}

let current: { close: () => void } | null = null;

export function openRecapStory(recap: MonthlyRecap, name: string, look?: RecapLook): void {
  current?.close();
  const slides = buildSlides(recap, name, look);
  const opener = document.activeElement as HTMLElement | null;
  const root = document.createElement("div");
  root.className = "recap-overlay";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.setAttribute("aria-label", rs("bannerTitle", { month: monthName(recap.month) }));
  root.tabIndex = -1;
  root.innerHTML = `
    <div class="recap-progress" aria-hidden="true">${slides.map(() => "<span><i></i></span>").join("")}</div>
    <button type="button" class="recap-close" aria-label="${escapeHtml(rs("close"))}">${icon("close")}</button>
    ${slides.map((slide) => `<section class="recap-slide tone-${slide.tone}" aria-hidden="true">${slide.html}</section>`).join("")}
    <button type="button" class="recap-tap prev" tabindex="-1" aria-hidden="true"></button>
    <button type="button" class="recap-tap next" tabindex="-1" aria-hidden="true"></button>
    <p class="recap-paused" aria-live="polite"></p>`;
  document.body.appendChild(root);
  document.body.classList.add("recap-open");

  const sections = Array.from(root.querySelectorAll<HTMLElement>(".recap-slide"));
  const fills = Array.from(root.querySelectorAll<HTMLElement>(".recap-progress i"));
  const paused = root.querySelector<HTMLElement>(".recap-paused")!;
  let index = 0;
  let elapsed = 0;
  let last = performance.now();
  let holding = false;
  let frame = 0;
  let holdTimer: ReturnType<typeof setTimeout> | null = null;
  const tg = getTelegramWebApp();

  const show = (next: number) => {
    index = Math.max(0, Math.min(slides.length - 1, next));
    elapsed = 0;
    sections.forEach((section, position) => {
      const on = position === index;
      section.classList.toggle("on", on);
      section.setAttribute("aria-hidden", on ? "false" : "true");
      if (on) {
        section.querySelectorAll<HTMLElement>(".a").forEach((el) => {
          el.style.animation = "none";
          void el.offsetHeight;
          el.style.animation = "";
        });
        section.querySelectorAll<HTMLElement>("[data-count]").forEach(countUp);
        slides[position].enter?.(section);
      }
    });
    fills.forEach((fill, position) => {
      fill.style.width = position < index ? "100%" : "0%";
    });
    try { tg?.HapticFeedback?.selectionChanged(); } catch { /* optional */ }
  };

  const tick = (now: number) => {
    const delta = now - last;
    last = now;
    if (!holding) elapsed += delta;
    const duration = slides[index].duration;
    if (Number.isFinite(duration)) {
      fills[index].style.width = `${Math.min(100, (elapsed / duration) * 100)}%`;
      if (elapsed >= duration && index < slides.length - 1) show(index + 1);
    } else {
      fills[index].style.width = "100%";
    }
    frame = requestAnimationFrame(tick);
  };

  const close = () => {
    cancelAnimationFrame(frame);
    document.removeEventListener("keydown", onKey);
    root.remove();
    document.body.classList.remove("recap-open");
    current = null;
    opener?.focus?.();
  };

  const onKey = (event: KeyboardEvent) => {
    if (event.key === "Escape") close();
    else if (event.key === "ArrowRight") show(index + 1);
    else if (event.key === "ArrowLeft") show(index - 1);
    else if (event.key === " ") {
      event.preventDefault();
      holding = !holding;
      paused.textContent = holding ? rs("pause") : "";
    }
  };

  const holdStart = () => {
    holdTimer = setTimeout(() => { holding = true; }, HOLD_TO_PAUSE_MS);
  };
  const holdEnd = (advance: number) => (event: Event) => {
    event.preventDefault();
    if (holdTimer) clearTimeout(holdTimer);
    const wasHolding = holding;
    holding = false;
    if (!wasHolding) show(index + advance);
  };
  const prev = root.querySelector<HTMLButtonElement>(".recap-tap.prev")!;
  const next = root.querySelector<HTMLButtonElement>(".recap-tap.next")!;
  prev.addEventListener("pointerdown", holdStart);
  next.addEventListener("pointerdown", holdStart);
  prev.addEventListener("click", holdEnd(-1));
  next.addEventListener("click", holdEnd(1));
  root.querySelector<HTMLButtonElement>(".recap-close")!.addEventListener("click", close);
  document.addEventListener("keydown", onKey);

  root.querySelector<HTMLButtonElement>("[data-recap-again]")?.addEventListener("click", () => show(0));
  root.querySelector<HTMLButtonElement>("[data-recap-share]")?.addEventListener("click", () => {
    void shareRecap(recap, root.querySelector<HTMLElement>("[data-recap-toast]"));
  });

  current = { close };
  show(0);
  last = performance.now();
  frame = requestAnimationFrame(tick);
  root.focus();
}

async function shareRecap(recap: MonthlyRecap, toast: HTMLElement | null): Promise<void> {
  const tg = getTelegramWebApp();
  const native = tg && typeof tg.shareMessage === "function" &&
    (typeof tg.isVersionAtLeast !== "function" || tg.isVersionAtLeast("8.0"));
  if (native) {
    try {
      const prepared = await prepareRecapShare(recap.month);
      tg!.shareMessage!(prepared.id);
      return;
    } catch {
      // No storage chat or Telegram throttling: fall back to the classic share link.
    }
  }
  const text = rs("shareText", { month: monthName(recap.month), solved: recap.solved ?? 0, played: recap.played });
  const url = `https://t.me/share/url?url=${encodeURIComponent(text)}`;
  if (tg?.openTelegramLink) tg.openTelegramLink(url);
  else window.open(url, "_blank", "noopener");
  if (toast) toast.textContent = "";
}
