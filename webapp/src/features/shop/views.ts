import { escapeHtml, weekNumber } from "@/utils/format";
import { t, getLanguage } from "@/i18n";
import { renderAvatar } from "@/components/Avatar";
import { DEFAULT_SQUARE_SYMBOLS } from "@/appearance";
import { getTelegramUser } from "@/telegram/webapp";
import type {
  ShopState,
  ShopCosmeticItem,
  ShopSubview,
  ShopKindFilter,
  ShopPriceFilter,
} from "./types";

const RARITY_COLOR: Record<string, string> = {
  free: "#8ea2b6",
  earned: "#38bd82",
  common: "#8ea2b6",
  rare: "#4dc4ff",
  collector: "#f0c74e",
};

const CELEBRATION_GLYPH: Record<string, string> = {
  spotlight: "🔦",
  confetti: "🎊",
  dust: "💨",
  flash: "📷",
  paper: "📄",
  snow: "❄️",
  mud: "🟫",
  fireworks: "🎆",
};

const SHOT_STOPS = [
  ["2018", "Club A"],
  ["2021", "Club B"],
  ["2024", "Club C"],
];

function previewDisplayName(): string {
  const user = getTelegramUser();
  return user?.first_name || t("common.anonymous");
}

export function itemMatches(
  item: ShopCosmeticItem,
  view: ShopSubview,
  kindFilter: ShopKindFilter,
  priceFilter: ShopPriceFilter,
  hideOwned: boolean,
): boolean {
  if (kindFilter !== "all" && item.kind !== kindFilter) return false;
  if (priceFilter !== "all" && item.price > Number(priceFilter)) return false;
  if (view === "wardrobe" && !item.owned) return false;
  const isEarned = Boolean(item.achievement || item.trophy || (item.completes && item.completes.length > 0));
  if (view === "achievements" && !isEarned) return false;
  if (view === "catalog" && (isEarned || (hideOwned && item.owned))) return false;
  return true;
}

export function legalLinks(): string {
  const lang = encodeURIComponent(getLanguage());
  return `
    <footer class="shop-legal-links">
      <a href="/privacy?lang=${lang}" target="_blank" rel="noopener">${escapeHtml(t("shop.privacy"))}</a>
      <a href="/terms?lang=${lang}#refunds" target="_blank" rel="noopener">${escapeHtml(t("shop.refunds"))}</a>
    </footer>
  `;
}

function rarityTag(item: ShopCosmeticItem): string {
  const rarity = item.rarity || "common";
  if (rarity === "free" || rarity === "common") return "";
  const color = RARITY_COLOR[rarity] || "#8ea2b6";
  const labelKey = `rarity${rarity.charAt(0).toUpperCase() + rarity.slice(1)}`;
  const label = t(`shop.${labelKey}` as any) || rarity;
  return `<span class="rarity" style="--rare-edge:${escapeHtml(color)}">${escapeHtml(label)}</span>`;
}

function themeShot(style: Record<string, unknown>): string {
  const edge = (style.edge as string) || "var(--edge)";
  const muted = (style.muted as string) || (style.text as string) || "var(--muted)";
  const bg = (style.card as string) || (style.bg as string) || "var(--card)";
  const accent = (style.accent as string) || "var(--accent)";
  const accentText = (style.accentText as string) || (style.bg as string) || "var(--accent-text)";

  return `
    <div class="theme-shot" aria-hidden="true" style="--shot-edge:${escapeHtml(edge)};background:${escapeHtml(bg)}">
      <div class="bar" style="color:${escapeHtml(muted)}">
        <span>${escapeHtml(t("common.appName"))}</span>
        <span style="color:${escapeHtml(accent)}">2/3</span>
      </div>
      ${SHOT_STOPS.map(
        ([year, club]) => `
        <div class="stop">
          <i style="background:${escapeHtml(accent)}"></i>
          <span style="color:${escapeHtml(muted)}">${escapeHtml(year)}</span>
          <b>${escapeHtml(club)}</b>
        </div>
      `,
      ).join("")}
      <div class="box" style="color:${escapeHtml(muted)};text-align:center">${escapeHtml(previewDisplayName())}</div>
      <div class="cta" style="background:${escapeHtml(accent)};color:${escapeHtml(accentText)}">
        ${escapeHtml(t("daily.guessBtn"))}
      </div>
    </div>
  `;
}

function shopArtwork(item: ShopCosmeticItem): string {
  const kind = item.kind;
  const style = item.style || {};
  const caption = `<div class="preview-caption">${escapeHtml(t("shop.tryOn"))}</div>`;

  if (kind === "theme") {
    const bg = (style.bg as string) || "var(--bg)";
    const pattern = (style.pattern as string) || "none";
    const text = (style.text as string) || "var(--text)";
    return `
      <div class="shop-stage" style="background-color:${escapeHtml(bg)};background-image:${escapeHtml(pattern)};color:${escapeHtml(text)}">
        ${caption}
        ${themeShot(style)}
      </div>
    `;
  }

  if (kind === "frame") {
    const ring = typeof style.ring === "string" ? `background:${style.ring}` : undefined;
    return `
      <div class="shop-stage">
        ${renderAvatar({ name: previewDisplayName(), ringStyle: ring, spinRing: false })}
        <div class="preview-name">${escapeHtml(previewDisplayName())}</div>
        ${caption}
      </div>
    `;
  }

  if (kind === "badge") {
    return `
      <div class="shop-stage">
        <div class="emoji-preview">${escapeHtml((style.emoji as string) || "—")}</div>
        <div class="preview-name">${escapeHtml(previewDisplayName())} ${escapeHtml((style.emoji as string) || "")}</div>
        ${caption}
      </div>
    `;
  }

  if (kind === "squares") {
    const correct = (style.correct as string) || DEFAULT_SQUARE_SYMBOLS.correct;
    const wrong = (style.wrong as string) || DEFAULT_SQUARE_SYMBOLS.wrong;
    const unused = (style.unused as string) || DEFAULT_SQUARE_SYMBOLS.unused;
    return `
      <div class="shop-stage">
        ${caption}
        <div class="preview-name">${escapeHtml(t("common.appName"))} · 2/3</div>
        <div class="emoji-preview">${escapeHtml(wrong + correct + unused)}</div>
      </div>
    `;
  }

  if (kind === "title") {
    const label = (style.label as string) || "—";
    const color = (style.color as string) || "var(--muted)";
    return `
      <div class="shop-stage">
        <div class="preview-name">${escapeHtml(previewDisplayName())}</div>
        <div class="title-tag" style="color:${escapeHtml(color)}">${escapeHtml(label)}</div>
        ${caption}
      </div>
    `;
  }

  if (kind === "number") {
    const num = (style.number as string) || "—";
    return `
      <div class="shop-stage">
        ${caption}
        <div class="emoji-preview number-glyph">${escapeHtml(num)}</div>
        <div class="preview-name">
          <span class="shirt">${escapeHtml(num)}</span>
          ${escapeHtml(previewDisplayName())}
        </div>
      </div>
    `;
  }

  if (kind === "celebration") {
    const glyph = CELEBRATION_GLYPH[(style.effect as string) || ""] || "✦";
    return `
      <div class="shop-stage">
        ${caption}
        <div class="emoji-preview">${escapeHtml(glyph)}</div>
        <div class="preview-name">${escapeHtml(item.name)}</div>
      </div>
    `;
  }

  if (kind === "card") {
    const finish = (style.finish as string) || "plain";
    const paper = (style.paper as string) || "#0a131e";
    const ink = (style.ink as string) || "#ecf2f8";
    const glow = (style.glow as string) || "#38bd82";
    return `
      <div class="shop-stage" style="padding:14px">
        <div class="fig-mini fig-${escapeHtml(finish)}" style="--paper:${escapeHtml(paper)};--ink:${escapeHtml(ink)};--glow:${escapeHtml(glow)}">
          <span class="n">#412</span>
          <span class="sq"><i></i><i class="on"></i><i class="off"></i></span>
          <span class="sc">2/3</span>
        </div>
      </div>
    `;
  }

  if (kind === "bundle" && item.contents && item.contents.length > 0) {
    const byKind = (k: string) =>
      (item.contents?.find((p) => p.kind === k) || {}).style || {};
    const theme = byKind("theme");
    const frame = byKind("frame");
    const title = byKind("title");
    const badge = byKind("badge");
    const squares = byKind("squares");

    const bg = (theme.bg as string) || "var(--bg)";
    const pattern = (theme.pattern as string) || "none";
    const text = (theme.text as string) || "var(--text)";
    const ring = typeof frame.ring === "string" ? `background:${frame.ring}` : undefined;
    const titleLabel = (title.label as string) || "";
    const titleColor = (title.color as string) || "var(--muted)";
    const badgeEmoji = (badge.emoji as string) || "";

    const correct = (squares.correct as string) || "";
    const wrong = (squares.wrong as string) || "";
    const unused = (squares.unused as string) || "";

    return `
      <div class="shop-stage" style="background-color:${escapeHtml(bg)};background-image:${escapeHtml(pattern)};color:${escapeHtml(text)}">
        ${caption}
        ${renderAvatar({ name: previewDisplayName(), ringStyle: ring, spinRing: false })}
        <div class="preview-name">${escapeHtml(previewDisplayName())} ${escapeHtml(badgeEmoji)}</div>
        ${titleLabel ? `<div class="title-tag" style="color:${escapeHtml(titleColor)}">${escapeHtml(titleLabel)}</div>` : ""}
        ${correct ? `<div class="emoji-preview">${escapeHtml(wrong + correct + unused)}</div>` : ""}
      </div>
    `;
  }

  return `<div class="emoji-preview">🎁</div>`;
}

export function renderShopCell(item: ShopCosmeticItem, state: ShopState): string {
  const kind = item.kind;
  const appearanceMutationBusy = Boolean(state.equippingItemId || state.lookMutation === "wear");
  const equipDisabled = appearanceMutationBusy ? "disabled" : "";
  let actionHtml = "";

  if (item.equipped) {
    actionHtml = `<div class="tag worn-tag">${escapeHtml(t("shop.worn"))}</div>`;
  } else if (item.owned && kind === "bundle") {
    actionHtml = `
      <div class="tag owned-tag">${escapeHtml(t("shop.owned"))}</div>
      ${
        item.equippable
          ? `<button type="button" class="btn ghost small" data-equip="${escapeHtml(item.id)}" ${equipDisabled}>${escapeHtml(t("shop.wearAll"))}</button>`
          : ""
      }
    `;
  } else if (item.owned) {
    actionHtml = `<button type="button" class="btn ghost small" data-equip="${escapeHtml(item.id)}" ${equipDisabled}>${escapeHtml(t("shop.wear"))}</button>`;
  } else if (item.achievement) {
    actionHtml = `
      <div class="shop-note">${escapeHtml(t("shop.earn"))} · ${item.progress}/${item.achievement.target}</div>
      <progress max="${item.achievement.target}" value="${item.progress}" aria-label="${escapeHtml(item.name)}"></progress>
    `;
  } else if (item.completes && item.completes.length > 0) {
    const missingPieces = item.completes.filter((piece) => !piece.owned);
    actionHtml = `
      <div class="shop-note">${escapeHtml(t("shop.completeMissing"))}: ${missingPieces.length}/${item.completes.length}</div>
      <progress max="${item.completes.length}" value="${item.completes.length - missingPieces.length}" aria-label="${escapeHtml(item.name)}"></progress>
    `;
  } else if (item.trophy) {
    actionHtml = `<div class="shop-note">${escapeHtml(t("shop.podiumOnly"))}</div>`;
  } else {
    actionHtml = `
      <button type="button" class="btn small buy-btn" data-buy="${escapeHtml(item.id)}" aria-label="${escapeHtml(t("shop.buy") + " " + item.name + " · " + item.price + " ⭐")}" ${state.buying ? "disabled" : ""}>
        ${escapeHtml(t("shop.buy"))} · ${item.price} ⭐
      </button>
    `;
  }

  const isPartial =
    kind === "bundle" && item.price > 0 && item.price < item.full_price;

  const previewTrigger =
    kind !== "bundle" || item.equippable
      ? `<button type="button" class="shop-preview-trigger" data-try="${escapeHtml(item.id)}" aria-label="${escapeHtml(t("shop.tryOn") + " · " + item.name)}">${escapeHtml(t("shop.tryOn"))} <span aria-hidden="true">↗</span></button>`
      : "";

  const sectionKey = `section${kind.charAt(0).toUpperCase() + kind.slice(1)}`;
  const kindLabel = t(`shop.${sectionKey}` as any) || kind;

  return `
    <article class="shop-item${item.equipped ? " worn" : ""}${item.featured ? " featured" : ""}" data-item-id="${escapeHtml(item.id)}">
      <div class="shop-artwork">
        ${rarityTag(item)}
        ${shopArtwork(item)}
        ${previewTrigger}
      </div>
      <div class="shop-product-head">
        <span class="shop-product-kind">${escapeHtml(kindLabel)}${item.featured ? " / 05" : ""}</span>
        <h3 class="nm">${escapeHtml(item.name)}</h3>
      </div>
      <div class="ds">
        <details class="shop-product-details">
          <summary>
            ${escapeHtml(t("shop.details"))}${kind === "bundle" ? ` · ${(item.contents || []).length} ${escapeHtml(t("shop.included"))}` : ""}
          </summary>
          <p>${escapeHtml(item.description)}</p>
          ${
            kind === "bundle"
              ? `<div class="pack-contents">${(item.contents || []).map((p) => `<span>${escapeHtml(p.name)}</span>`).join("")}</div>`
              : ""
          }
        </details>
        ${item.achievement && item.owned ? `<p class="shop-unlocked">✧ ${escapeHtml(t("shop.unlocked"))}</p>` : ""}
        ${
          isPartial
            ? `
          <p class="shop-completion">
            <b>${escapeHtml(t("shop.partial"))}</b><br>
            ${escapeHtml(t("shop.missing"))}: ${(item.contents || [])
                .filter((p) => !p.owned)
                .map((p) => escapeHtml(p.name))
                .join(", ")}
          </p>
        `
            : ""
        }
      </div>
      <div class="shop-product-actions">
        ${actionHtml}
      </div>
    </article>
  `;
}

export function renderWeeklyShowcase(state: ShopState): string {
  const showcase = state.catalogue?.showcase;
  if (!showcase || !showcase.items || showcase.items.length === 0) {
    return "";
  }
  const weekNum = weekNumber(showcase.week);
  return `
    <div class="card shop-section" id="shelf-showcase">
      <div class="showcase-strip">
        <h2>${escapeHtml(t("shop.showcaseTitle"))}</h2>
        <span class="when">${escapeHtml(t("shop.showcaseWeek", { n: weekNum }))}</span>
      </div>
      <div class="shop-grid">
        ${showcase.items.map((item) => renderShopCell(item, state)).join("")}
      </div>
    </div>
  `;
}

export function renderSavedLooks(state: ShopState): string {
  const looks = state.catalogue?.looks || [];
  const wearDisabled = state.equippingItemId || state.lookMutation ? "disabled" : "";
  return `
    <div class="card shop-saved-looks">
      <h2>${escapeHtml(t("shop.looksTitle"))}</h2>
      <div class="shop-controls save-look-form">
        <input id="look-name" maxlength="30" aria-label="${escapeHtml(t("shop.lookNamePlaceholder"))}" placeholder="${escapeHtml(t("shop.lookNamePlaceholder"))}">
        <button type="button" class="btn small" id="shop-save-look" ${state.preview ? "disabled" : ""}>${escapeHtml(t("shop.saveLook"))}</button>
      </div>
      <div class="saved-looks-list">
        ${
          looks.length === 0
            ? `<p class="muted looks-empty">${escapeHtml(t("shop.noSavedLooks"))}</p>`
            : looks
                .map(
                  (look) => `
          <div class="saved-look-row">
            <span class="look-name">${escapeHtml(look.name)}</span>
            <div class="look-actions">
              <button type="button" class="btn ghost small" data-use-look="${escapeHtml(look.name)}" ${wearDisabled}>${escapeHtml(t("shop.wear"))}</button>
              <button type="button" class="btn ghost small delete-btn" data-delete-look="${escapeHtml(look.name)}">${escapeHtml(t("shop.deleteLook"))}</button>
            </div>
          </div>
        `,
                )
                .join("")
        }
      </div>
    </div>
  `;
}

export function renderPurchaseHistory(state: ShopState): string {
  if (state.historyStatus === "loading") {
    return `<div class="card center muted">${escapeHtml(t("common.loading"))}</div>`;
  }
  if (state.historyStatus === "error") {
    return `
      <div class="card error-card">
        <p class="error-msg">${escapeHtml(state.historyError || t("shop.loadError"))}</p>
        <button type="button" class="btn small" id="shop-history-retry">${escapeHtml(t("shop.retry"))}</button>
      </div>
    `;
  }
  const history = state.history;
  if (!history || !history.purchases || history.purchases.length === 0) {
    return `<p class="card center muted">${escapeHtml(t("shop.noHistory"))}</p>`;
  }

  return history.purchases
    .map(
      (purchase, index) => `
      <div class="card purchase-row">
        <b>${escapeHtml(purchase.name)}</b>
        <p class="purchase-meta">${escapeHtml(purchase.day)} · ${escapeHtml(String(purchase.stars))} ⭐ · ${escapeHtml(purchase.refunded ? t("shop.refunded") : t("shop.paid"))}</p>
        <details class="purchase-support-details">
          <summary>${escapeHtml(t("shop.support"))}</summary>
          <p class="shop-note">${escapeHtml(t("shop.supportHint"))}</p>
          <textarea class="history-command" id="support-${index}" readonly aria-label="${escapeHtml(t("shop.support"))}">/paysupport ${escapeHtml(t("shop.supportRequest"))} ${escapeHtml(purchase.charge_id)}</textarea>
          <div class="history-actions">
            <button type="button" class="btn ghost small" data-copy-support="${index}">${escapeHtml(t("shop.copyCommand"))}</button>
            ${
              history.support_url
                ? `<a class="btn ghost small" href="${escapeHtml(history.support_url)}" target="_blank" rel="noopener">${escapeHtml(t("shop.openBot"))}</a>`
                : ""
            }
          </div>
        </details>
      </div>
    `,
    )
    .join("");
}

export function renderPreviewBar(state: ShopState): string {
  if (!state.preview) return "";
  const item = state.preview.item;
  const worn = state.preview.appearance;

  const ring = typeof worn.frame?.ring === "string" ? `background:${worn.frame.ring}` : undefined;
  const titleTag = worn.title?.label
    ? `<div class="title-tag" style="color:${escapeHtml(worn.title.color || "var(--muted)")}">${escapeHtml(worn.title.label)}</div>`
    : "";
  const squaresStr = (worn.squares?.wrong || "🟥") + (worn.squares?.correct || "🟩") + (worn.squares?.unused || "⬜");

  return `
    <aside class="preview-bar" aria-label="${escapeHtml(t("shop.previewTrying"))}">
      <div class="preview-bar-head">
        <b>${escapeHtml(t("shop.previewTrying"))} · ${escapeHtml(item.name)}</b>
        <button type="button" class="btn ghost small" id="shop-stop-preview">${escapeHtml(t("shop.stopPreview"))}</button>
      </div>
      <div class="preview-person">
        ${renderAvatar({ name: previewDisplayName(), ringStyle: ring, spinRing: false, size: "small" })}
        <div class="preview-meta">
          <div class="preview-identity">
            ${worn.number ? `<span class="shirt">${escapeHtml(worn.number)}</span>` : ""}
            <span>${escapeHtml(previewDisplayName())} ${escapeHtml(worn.badge || "")}</span>
          </div>
          ${titleTag}
          <div class="preview-squares">${escapeHtml(squaresStr)}</div>
        </div>
      </div>
      <p class="shop-note">${escapeHtml(t("shop.previewHint"))}</p>
    </aside>
  `;
}

export function renderShopSection(
  kind: string,
  items: ShopCosmeticItem[],
  state: ShopState,
  heading?: string,
  shelf = kind,
): string {
  const sectionKey = `section${kind.charAt(0).toUpperCase() + kind.slice(1)}`;
  const title = heading || t(`shop.${sectionKey}` as any) || kind;

  return `
    <div class="card shop-section" id="shelf-${escapeHtml(shelf)}">
      <div class="shop-section-heading">
        <h2>${escapeHtml(title)}</h2>
        <span>${String(items.length).padStart(2, "0")}</span>
      </div>
      <div class="shop-grid${kind === "bundle" ? " wide" : ""}">
        ${items.map((item) => renderShopCell(item, state)).join("")}
      </div>
    </div>
  `;
}

export function renderShopPage(state: ShopState): string {
  if (state.status === "loading" && !state.catalogue) {
    return `
      <section class="shop-shell">
        <div class="card center muted shop-loading" role="status">
          ${escapeHtml(t("common.loading"))}
        </div>
      </section>
    `;
  }

  if (state.status === "error" && !state.catalogue) {
    return `
      <section class="shop-shell">
        <div class="card error-card">
          <p class="error-msg">${escapeHtml(state.errorMessage || t("shop.loadError"))}</p>
          <button type="button" class="btn" id="shop-retry">${escapeHtml(t("shop.retry"))}</button>
        </div>
      </section>
    `;
  }

  const introHtml = `
    <header class="shop-hero">
      <div class="shop-heading">
        <span class="shop-kicker">${escapeHtml(t("shop.kicker"))} <span>/ ${escapeHtml(t("shop.title"))}</span></span>
        <h2>${escapeHtml(t("shop.headline"))}</h2>
        <p>${escapeHtml(t("shop.subtitle"))}</p>
      </div>
      <div class="shop-pitch-art" aria-hidden="true">
        <span class="pitch-circle"></span>
        <span class="pitch-line"></span>
        <span class="pitch-ball">✦</span>
      </div>
      <div class="shop-trust">
        <details>
          <summary>✦ ${escapeHtml(t("shop.cosmeticsOnly"))} <span>· Telegram Stars</span></summary>
          <p>${escapeHtml(t("shop.starsExplanation"))}</p>
        </details>
        ${legalLinks()}
      </div>
    </header>
  `;

  const views: ShopSubview[] = ["catalog", "wardrobe", "achievements", "history"];
  const viewIcons: Record<ShopSubview, string> = {
    catalog: "◇",
    wardrobe: "▣",
    achievements: "✧",
    history: "≡",
  };

  const tabsHtml = `
    <div class="shop-controls shop-tabs" role="tablist" aria-label="${escapeHtml(t("shop.title"))}">
      ${views
        .map(
          (view) => `
        <button type="button" role="tab" data-shop-view="${view}" aria-selected="${state.view === view}" class="shop-tab-btn${state.view === view ? " active" : ""}">
          <span class="shop-tab-icon" aria-hidden="true">${viewIcons[view]}</span>
          ${escapeHtml(t(`shop.${view}` as any))}
        </button>
      `,
        )
        .join("")}
    </div>
  `;

  const deliveryBanner =
    state.deliveryStatus === "delivering"
      ? `<div class="shop-delivery-banner" role="status">${escapeHtml(t("shop.waitingDelivery"))}</div>`
      : state.deliveryStatus === "pending"
        ? `<div class="shop-delivery-banner pending" role="status">${escapeHtml(t("shop.deliveryPending"))}</div>`
        : "";

  const toastHtml = state.toast
    ? `<div class="toast" role="status">${escapeHtml(state.toast)}</div>`
    : "";

  if (state.view === "history") {
    return `
      <section class="shop-shell">
        ${renderPreviewBar(state)}
        ${deliveryBanner}
        ${introHtml}
        ${tabsHtml}
        <div class="history-container">
          ${renderPurchaseHistory(state)}
        </div>
        ${toastHtml}
      </section>
    `;
  }

  const kinds: Array<{ key: ShopKindFilter; label: string }> = [
    { key: "all", label: t("shop.allCategories") },
    { key: "theme", label: t("shop.sectionTheme") },
    { key: "frame", label: t("shop.sectionFrame") },
    { key: "title", label: t("shop.sectionTitle") },
    { key: "badge", label: t("shop.sectionBadge") },
    { key: "squares", label: t("shop.sectionSquares") },
    { key: "number", label: t("shop.sectionNumber") },
    { key: "celebration", label: t("shop.sectionCelebration") },
    { key: "card", label: t("shop.sectionCard") },
    { key: "bundle", label: t("shop.sectionBundle") },
  ];

  const prices: Array<{ key: ShopPriceFilter; label: string }> = [
    { key: "all", label: t("shop.anyPrice") },
    { key: "15", label: "≤ 15 ⭐" },
    { key: "25", label: "≤ 25 ⭐" },
    { key: "55", label: "≤ 55 ⭐" },
    { key: "75", label: "≤ 75 ⭐" },
  ];

  const filtersHtml = `
    <div class="shop-controls shop-filters" role="search" aria-label="${escapeHtml(t("shop.allCategories"))}">
      <select id="shop-kind" aria-label="${escapeHtml(t("shop.allCategories"))}">
        ${kinds
          .map(
            (k) => `
          <option value="${k.key}" ${state.kindFilter === k.key ? "selected" : ""}>${escapeHtml(k.label)}</option>
        `,
          )
          .join("")}
      </select>
      <select id="shop-price" aria-label="${escapeHtml(t("shop.anyPrice"))}">
        ${prices
          .map(
            (p) => `
          <option value="${p.key}" ${state.priceFilter === p.key ? "selected" : ""}>${escapeHtml(p.label)}</option>
        `,
          )
          .join("")}
      </select>
      ${
        state.view === "catalog"
          ? `
        <label class="shop-filter-checkbox">
          <input id="shop-hide-owned" type="checkbox" ${state.hideOwned ? "checked" : ""}>
          <span>${escapeHtml(t("shop.hideOwned"))}</span>
        </label>
      `
          : ""
      }
    </div>
  `;

  const catalogue = state.catalogue;
  const rawBundles = catalogue?.bundles || [];
  const rawSections = catalogue?.sections || [];

  const filterItem = (item: ShopCosmeticItem) =>
    itemMatches(item, state.view, state.kindFilter, state.priceFilter, state.hideOwned);

  const visibleBundles = rawBundles.filter(filterItem);
  const visibleSections = rawSections
    .map((sec) => ({
      kind: sec.kind,
      items: sec.items.filter(filterItem),
    }))
    .filter((sec) => sec.items.length > 0);

  const featuredCollections = visibleBundles.filter((b) => b.featured);
  const regularBundles = visibleBundles.filter((b) => !b.featured);

  const collectionsHtml =
    featuredCollections.length > 0
      ? renderShopSection("bundle", featuredCollections, state, t("shop.sectionCollections"), "collections")
      : "";

  const bundlesHtml =
    regularBundles.length > 0
      ? renderShopSection("bundle", regularBundles, state, t("shop.sectionBundle"), "bundle")
      : "";

  const shelvesHtml = visibleSections
    .map((sec) => renderShopSection(sec.kind, sec.items, state))
    .join("");

  const shortcutKinds = (regularBundles.length > 0 ? ["bundle"] : []).concat(
    visibleSections.map((s) => s.kind),
  );

  const shortcutsHtml =
    featuredCollections.length > 0 || shortcutKinds.length > 0
      ? `
    <div class="shop-shortcuts" aria-label="${escapeHtml(t("shop.shortcutsNav"))}">
      ${featuredCollections.length > 0 ? `<a href="#shelf-collections">${escapeHtml(t("shop.sectionCollectionsNav"))}</a>` : ""}
      ${shortcutKinds
        .map((k) => {
          const sKey = `section${k.charAt(0).toUpperCase() + k.slice(1)}`;
          return `<a href="#shelf-${escapeHtml(k)}">${escapeHtml(t(`shop.${sKey}` as any) || k)}</a>`;
        })
        .join("")}
    </div>
  `
      : "";

  const showcaseHtml = state.view === "catalog" ? renderWeeklyShowcase(state) : "";
  const savedLooksHtml = state.view === "wardrobe" ? renderSavedLooks(state) : "";

  const contentShelves = collectionsHtml + bundlesHtml + shelvesHtml;
  const emptyHtml = `<p class="card center muted">${escapeHtml(t("shop.empty"))}</p>`;

  return `
    <section class="shop-shell">
      ${renderPreviewBar(state)}
      ${deliveryBanner}
      ${introHtml}
      ${tabsHtml}
      ${savedLooksHtml}
      ${showcaseHtml}
      ${filtersHtml}
      ${shortcutsHtml}
      ${contentShelves || emptyHtml}
      ${toastHtml}
    </section>
  `;
}
