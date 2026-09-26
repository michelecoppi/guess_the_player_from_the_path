import { renderCardSample, renderFormation } from '@/components/CosmeticArt';
import { renderStyleInventory } from "@/components/StyleInventory";
import { escapeHtml, weekNumber } from "@/utils/format";
import { t, getLanguage } from "@/i18n";
import { renderAvatar } from "@/components/Avatar";
import { icon } from "@/components/Icon";
import { legalHref } from "@/components/LegalLinks";
import { profileSurfaceAttributes } from "@/appearance/surfaces";
import { DEFAULT_SQUARE_SYMBOLS, parseResolvedAppearance, skinTokens } from "@/appearance";
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
  stadium_wave: "〰️",
  petals: "🌸",
  pixels: "👾",
  comets: "☄️",
  bubbles: "🫧",
  flares: "🎇",
  lightning: "⚡",
  bounce: "⚽",
};

const SHOT_STOPS = [
  ["2018", "Club A"],
  ["2021", "Club B"],
  ["2024", "Club C"],
];

function searchable(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase();
}

function localizedTitle(style: Record<string, unknown>): string {
  const labels = style.label_i18n;
  const label = labels && typeof labels === 'object' ? (labels as Record<string, unknown>)[getLanguage()] : undefined;
  return typeof label === 'string' ? label : typeof style.label === 'string' ? style.label : '';
}

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
  return `
    <footer class="shop-legal-links">
      <a href="${legalHref("privacy")}" target="_blank" rel="noopener">${escapeHtml(t("shop.privacy"))}</a>
      <a href="${legalHref("terms", "refunds")}" target="_blank" rel="noopener">${escapeHtml(t("shop.refunds"))}</a>
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
  // Decorative theme colours only: text and the primary action stay product-owned.
  const skin = skinTokens(parseResolvedAppearance({ theme: style }));
  const edge = skin["--skin-accent-secondary"] || "var(--edge)";
  const muted = "var(--muted)";
  const bg = "color-mix(in srgb, var(--card) 55%, transparent)";
  const accent = skin["--skin-accent"] || "var(--accent)";
  const accentText = "var(--accent-text)";

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
      <div class="cta" style="background:var(--accent);color:${escapeHtml(accentText)}">
        ${escapeHtml(t("daily.guessBtn"))}
      </div>
    </div>
  `;
}

interface ShopArtworkOptions {
  /**
   * Whether to render the wearer's own avatar/name inside the artwork. The try-on bar
   * already shows the wearer's identity once (with this item applied) in its own
   * "preview-person" panel, so its product-detail panel renders artwork with this off
   * to avoid showing that same avatar/name a second time (#90). The catalogue grid has
   * no separate identity panel, so its cells keep the default (identity shown).
   */
  showIdentity?: boolean;
}

function shopArtwork(item: ShopCosmeticItem, opts: ShopArtworkOptions = {}): string {
  const showIdentity = opts.showIdentity !== false;
  const kind = item.kind;
  const style = item.style || {};
  const caption = `<div class="preview-caption">${escapeHtml(t("shop.tryOn"))}</div>`;

  if (kind === "theme") {
    // The stage shows the same surface the owner's profile will get.
    return `
      <div class="shop-stage theme-stage" ${profileSurfaceAttributes({ theme: style }).replace("data-cosmetic-profile ", "")}>
        ${caption}
        ${renderFormation({ theme: style })}${themeShot(style)}
      </div>
    `;
  }

  if (kind === "frame") {
    const ring = typeof style.ring === "string" ? `background:${style.ring}` : undefined;
    const identityHtml = showIdentity
      ? `${renderAvatar({ name: previewDisplayName(), ringStyle: ring, spinRing: false, tactics: parseResolvedAppearance({ frame: style }).frame?.tactics, ringMotion: parseResolvedAppearance({ frame: style }).frame?.motion })}
         <div class="preview-name">${escapeHtml(previewDisplayName())}</div>`
      : "";
    return `
      <div class="shop-stage">
        ${identityHtml}
        ${caption}
      </div>
    `;
  }

  if (kind === "badge") {
    return `
      <div class="shop-stage">
        <div class="emoji-preview">${escapeHtml((style.emoji as string) || "—")}</div>
        ${showIdentity ? `<div class="preview-name">${escapeHtml(previewDisplayName())} ${escapeHtml((style.emoji as string) || "")}</div>` : ""}
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
    const label = localizedTitle(style) || "—";
    const color = (style.color as string) || "var(--muted)";
    return `
      <div class="shop-stage">
        ${showIdentity ? `<div class="preview-name">${escapeHtml(previewDisplayName())}</div>` : ""}
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
        ${
          showIdentity
            ? `<div class="preview-name">
                 <span class="shirt">${escapeHtml(num)}</span>
                 ${escapeHtml(previewDisplayName())}
               </div>`
            : ""
        }
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
    return `<div class="shop-stage shop-card-art">${renderCardSample(style)}</div>`;
  }

  if (kind === "bundle" && item.contents && item.contents.length > 0) {
    const byKind = (k: string) =>
      (item.contents?.find((p) => p.kind === k) || {}).style || {};
    const theme = byKind("theme");
    const frame = byKind("frame");
    const title = byKind("title");
    const badge = byKind("badge");
    const squares = byKind("squares");

    const ring = typeof frame.ring === "string" ? `background:${frame.ring}` : undefined;
    const titleLabel = localizedTitle(title);
    const titleColor = (title.color as string) || "var(--muted)";
    const badgeEmoji = (badge.emoji as string) || "";

    const correct = (squares.correct as string) || "";
    const wrong = (squares.wrong as string) || "";
    const unused = (squares.unused as string) || "";

    const identityHtml = showIdentity
      ? `${renderAvatar({ name: previewDisplayName(), ringStyle: ring, spinRing: false, tactics: parseResolvedAppearance({ frame }).frame?.tactics, ringMotion: parseResolvedAppearance({ frame }).frame?.motion })}
         <div class="preview-name">${escapeHtml(previewDisplayName())} ${escapeHtml(badgeEmoji)}</div>`
      : badgeEmoji
        ? `<div class="emoji-preview">${escapeHtml(badgeEmoji)}</div>`
        : "";

    return `
      <div class="shop-stage bundle-stage" ${profileSurfaceAttributes({ theme }).replace("data-cosmetic-profile", "data-cosmetic-preview")}>
        ${caption}
        ${identityHtml}
        ${titleLabel ? `<div class="title-tag" style="color:${escapeHtml(titleColor)}">${escapeHtml(titleLabel)}</div>` : ""}
        ${correct ? `<div class="emoji-preview">${escapeHtml(wrong + correct + unused)}</div>` : ""}
        ${renderCardSample(byKind("card"))}
        ${renderFormation({ theme })}
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
  } else if (item.owned && item.equippable) {
    actionHtml = `<button type="button" class="btn ghost small" data-equip="${escapeHtml(item.id)}" ${equipDisabled}>${escapeHtml(t("shop.wear"))}</button>`;
  } else if (item.owned) {
    actionHtml = `<span class="tag owned-tag">${escapeHtml(t("shop.owned"))}</span>`;
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

  // Trying on what's already worn would just show what's already on screen - no button.
  const previewTrigger =
    !item.equipped && (kind !== "bundle" || item.equippable)
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
        <span class="shop-product-kind">${escapeHtml(kindLabel)}</span>
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
    <aside class="preview-bar" tabindex="-1" aria-label="${escapeHtml(t("shop.previewTrying"))}">
      <div class="preview-bar-head">
        <b>${escapeHtml(t("shop.previewTrying"))} · ${escapeHtml(item.name)}</b>
        <button type="button" class="btn ghost small" id="shop-stop-preview">${escapeHtml(t("shop.stopPreview"))}</button>
      </div>
      <div class="preview-layout">
      <div class="preview-profile" ${profileSurfaceAttributes(worn)}>
      <p class="eyebrow">${escapeHtml(t('profile.title'))}</p>
      ${renderFormation(worn)}
      <div class="preview-person">
        ${renderAvatar({ name: previewDisplayName(), ringStyle: ring, spinRing: false, tactics: worn.frame?.tactics, ringMotion: worn.frame?.motion, size: "large" })}
        <div class="preview-meta">
          <div class="preview-identity">
            ${worn.number ? `<span class="shirt">${escapeHtml(worn.number)}</span>` : ""}
            <span>${escapeHtml(previewDisplayName())} ${escapeHtml(worn.badge || "")}</span>
          </div>
          ${titleTag}
          <div class="preview-squares">${escapeHtml(squaresStr)}</div>
        </div>
      </div>
      </div>
      <div class="preview-product">
      <div class="preview-item-detail">${shopArtwork(item, { showIdentity: false })}</div>
      <h3 class="preview-product-name">${escapeHtml(item.name)}</h3>
      <p class="preview-description">${escapeHtml(item.description)}</p>
      ${item.owned && item.equippable ? `<button type="button" class="btn" data-equip="${escapeHtml(item.id)}" ${item.equipped || state.equippingItemId || state.lookMutation ? 'disabled' : ''}>${escapeHtml(t(item.equipped ? 'shop.worn' : 'shop.wear'))}</button>` : ''}
      <p class="shop-note">${escapeHtml(t("shop.previewHint"))}</p>
      </div></div>
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

function renderShopTile(item: ShopCosmeticItem): string {
  const sectionKey = `section${item.kind.charAt(0).toUpperCase() + item.kind.slice(1)}`;
  const status = item.equipped
    ? t("shop.worn")
    : item.owned
      ? t("shop.owned")
      : item.price > 0
        ? `${item.price} ⭐`
        : item.free ? t("shop.rarityFree") : t("shop.earn");
  return `
    <article class="shop-tile" data-item-id="${escapeHtml(item.id)}">
      <div class="shop-tile-art">${shopArtwork(item)}</div>
      <div class="shop-tile-meta"><span>${escapeHtml(t(`shop.${sectionKey}` as any) || item.kind)}</span><strong>${escapeHtml(status)}</strong></div>
      <h3>${escapeHtml(item.name)}</h3>
      <button type="button" class="shop-tile-open" data-shop-detail="${escapeHtml(item.id)}" aria-label="${escapeHtml(t("shop.details") + " · " + item.name)}">${escapeHtml(t("shop.details"))} →</button>
    </article>`;
}

function renderShopDetail(item: ShopCosmeticItem, state: ShopState): string {
  const sectionKey = `section${item.kind.charAt(0).toUpperCase() + item.kind.slice(1)}`;
  const placeKey = `place${item.kind.charAt(0).toUpperCase() + item.kind.slice(1)}`;
  const isEarned = Boolean(item.achievement || item.trophy || item.completes.length);
  const partial = item.kind === "bundle" && item.price < item.full_price;
  const action = item.equipped
    ? `<span class="tag worn-tag">${escapeHtml(t("shop.worn"))}</span>`
    : item.owned
      ? item.equippable
        ? `<button type="button" class="btn" data-equip="${escapeHtml(item.id)}" ${state.equippingItemId || state.lookMutation ? "disabled" : ""}>${escapeHtml(t(item.kind === "bundle" ? "shop.wearAll" : "shop.wear"))}</button>`
        : `<span class="tag owned-tag">${escapeHtml(t("shop.owned"))}</span>`
      : isEarned
        ? item.achievement
          ? `<p>${escapeHtml(t("shop.earn"))} · ${item.progress}/${item.achievement.target}</p><progress max="${item.achievement.target}" value="${item.progress}"></progress>`
          : `<p>${escapeHtml(t(item.trophy ? "shop.podiumOnly" : "shop.completeMissing"))}</p>`
        : `<button type="button" class="btn buy-btn" data-buy="${escapeHtml(item.id)}" ${state.buying ? "disabled" : ""}>${escapeHtml(t("shop.buy"))} · ${item.price} ⭐</button>`;

  return `
    <section class="shop-detail" aria-labelledby="shop-detail-title">
      <button type="button" class="shop-back" id="shop-detail-back">← ${escapeHtml(t("shop.backToShop"))}</button>
      <div class="shop-detail-layout">
        <div class="shop-detail-art">${shopArtwork(item)}</div>
        <div class="shop-detail-info">
          <span class="shop-product-kind">${escapeHtml(t(`shop.${sectionKey}` as any) || item.kind)}</span>
          <h2 id="shop-detail-title">${escapeHtml(item.name)}</h2>
          <p>${escapeHtml(item.description)}</p>
          <div class="shop-detail-place"><b>${escapeHtml(t("shop.whereSeen"))}</b><span>${escapeHtml(t(`shop.${placeKey}` as any))}</span></div>
          ${item.kind === "bundle" ? `
            <h3>${escapeHtml(t("shop.included"))}</h3>
            <ul class="shop-detail-pieces">${(item.contents || []).map((piece) => `<li><span>${escapeHtml(piece.name)}</span><span>${escapeHtml(t(piece.owned ? "shop.owned" : "shop.missing"))}</span></li>`).join("")}</ul>
          ` : ""}
          ${!item.owned && !isEarned ? `<p class="shop-detail-price">${item.price} ⭐ ${partial ? `<small>${escapeHtml(t("shop.partial"))}</small>` : ""}</p>` : ""}
          <div class="shop-detail-actions">
            ${!item.equipped && (item.kind !== "bundle" || item.equippable) ? `<button type="button" class="btn ghost" data-try="${escapeHtml(item.id)}">${escapeHtml(t("shop.tryOn"))}</button>` : ""}
            ${action}
          </div>
          <p class="shop-note">${escapeHtml(t("shop.cosmeticsOnly"))} · Telegram Stars</p>
        </div>
      </div>
    </section>
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

  const views: ShopSubview[] = ["discover", "catalog", "wardrobe"];
  const viewIcons: Record<ShopSubview, string> = {
    discover: icon('shop'),
    catalog: icon('shop'),
    wardrobe: icon('profile'),
    achievements: icon('ranking'),
    history: icon('archive'),
  };

  const tabsHtml = `
    <div class="shop-controls shop-tabs" role="tablist" aria-label="${escapeHtml(t("shop.title"))}">
      ${views
        .map(
          (view) => `
        <button type="button" role="tab" data-shop-view="${view}" aria-selected="${state.view === view || (view === "wardrobe" && (state.view === "achievements" || state.view === "history"))}" class="shop-tab-btn${state.view === view || (view === "wardrobe" && (state.view === "achievements" || state.view === "history")) ? " active" : ""}">
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

  const secondaryLinks = `
    <div class="shop-secondary-nav">
      <button type="button" data-shop-view="achievements">${escapeHtml(t("shop.achievements"))} ↗</button>
      <button type="button" data-shop-view="history">${escapeHtml(t("shop.history"))} ↗</button>
    </div>`;

  const selected = state.selectedItemId && state.catalogue
    ? [...state.catalogue.bundles, ...state.catalogue.sections.flatMap((section) => section.items)]
        .find((item) => item.id === state.selectedItemId)
    : undefined;
  if (selected) {
    return `<section class="shop-shell">${renderPreviewBar(state)}${deliveryBanner}${renderShopDetail(selected, state)}${legalLinks()}${toastHtml}</section>`;
  }

  if (state.view === "discover") {
    const collections = (state.catalogue?.bundles || []).filter((item) => item.featured)
      .sort((left, right) => Number(left.owned) - Number(right.owned)).slice(0, 3);
    const picks = (state.catalogue?.showcase?.items || []).filter((item) => !collections.some((one) => one.id === item.id))
      .sort((left, right) => Number(left.owned) - Number(right.owned)).slice(0, 3);
    return `
      <section class="shop-shell shop-discover">
        ${renderPreviewBar(state)}${deliveryBanner}${introHtml}${tabsHtml}
        <div class="shop-discover-intro">
          <div><span class="shop-kicker">${escapeHtml(t("shop.discover"))}</span><h2>${escapeHtml(t("shop.discoverTitle"))}</h2><p>${escapeHtml(t("shop.discoverSubtitle"))}</p></div>
          <button type="button" class="btn" data-shop-view="catalog">${escapeHtml(t("shop.browseAll"))} →</button>
        </div>
        ${collections.length ? `<section class="shop-section" id="shelf-collections"><div class="shop-section-heading"><h2>${escapeHtml(t("shop.sectionCollections"))}</h2></div><div class="shop-grid wide">${collections.map(renderShopTile).join("")}</div></section>` : ""}
        ${picks.length ? `<section class="shop-section"><div class="shop-section-heading"><h2>${escapeHtml(t("shop.showcaseTitle"))}</h2></div><div class="shop-grid">${picks.map(renderShopTile).join("")}</div></section>` : ""}
        ${secondaryLinks}${toastHtml}
      </section>`;
  }

  if (state.view === "history") {
    return `
      <section class="shop-shell">
        ${renderPreviewBar(state)}
        ${deliveryBanner}
        ${introHtml}
        ${tabsHtml}
        ${secondaryLinks}
        <div class="history-container">
          ${renderPurchaseHistory(state)}
        </div>
        ${toastHtml}
      </section>
    `;
  }

  if (state.view === "wardrobe") {
    const owned = [
      ...(state.catalogue?.bundles || []),
      ...(state.catalogue?.sections || []).flatMap((section) => section.items),
    ].filter((item) => item.owned && !item.free);
    return `
      <section class="shop-shell shop-wardrobe">
        ${renderPreviewBar(state)}${deliveryBanner}${introHtml}${tabsHtml}${secondaryLinks}
        ${renderStyleInventory([], state.catalogue!.sections.flatMap((section) => section.items).filter((item) => item.owned), state.catalogue!.equipped)}
        ${renderSavedLooks(state)}
        <section class="shop-section"><div class="shop-section-heading"><h2>${escapeHtml(t("shop.wardrobe"))}</h2><span>${owned.length}</span></div>
          ${owned.length ? `<div class="shop-grid">${owned.map(renderShopTile).join("")}</div>` : `<p class="card center muted">${escapeHtml(t("shop.noOwnedItems"))}</p>`}
        </section>
        ${toastHtml}
      </section>`;
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
    { key: "7", label: "≤ 7 ⭐" },
    { key: "12", label: "≤ 12 ⭐" },
    { key: "28", label: "≤ 28 ⭐" },
    { key: "38", label: "≤ 38 ⭐" },
  ];

  if (state.view === "catalog") {
    const query = searchable(state.searchQuery.trim());
    const all = [
      ...(state.catalogue?.bundles || []),
      ...(state.catalogue?.sections || []).flatMap((section) => section.items),
    ];
    const matches = all.filter((item) =>
      itemMatches(item, "catalog", state.kindFilter, state.priceFilter, state.hideOwned)
      && (!query || searchable(`${item.name} ${item.description}`).includes(query)),
    ).sort((left, right) => Number(left.owned) - Number(right.owned));
    const shown = matches.slice(0, state.visibleCount);
    return `
      <section class="shop-shell shop-catalog">
        ${renderPreviewBar(state)}${deliveryBanner}${introHtml}${tabsHtml}
        <div class="shop-catalog-header"><h2>${escapeHtml(t("shop.catalog"))}</h2><p>${escapeHtml(t("shop.catalogIntro"))}</p></div>
        <label class="shop-search-label" for="shop-search">${escapeHtml(t("shop.searchLabel"))}</label>
        <input id="shop-search" type="search" value="${escapeHtml(state.searchQuery)}" placeholder="${escapeHtml(t("shop.searchPlaceholder"))}" autocomplete="off">
        <div class="shop-categories" aria-label="${escapeHtml(t("shop.allCategories"))}">
          ${kinds.map((kind) => `<button type="button" data-shop-kind="${kind.key}" aria-pressed="${state.kindFilter === kind.key}">${escapeHtml(kind.label)}</button>`).join("")}
        </div>
        <div class="shop-catalog-tools">
          <label>${escapeHtml(t("shop.anyPrice"))}<select id="shop-price">${prices.map((price) => `<option value="${price.key}" ${state.priceFilter === price.key ? "selected" : ""}>${escapeHtml(price.label)}</option>`).join("")}</select></label>
          <label class="shop-filter-checkbox"><input id="shop-hide-owned" type="checkbox" ${state.hideOwned ? "checked" : ""}>${escapeHtml(t("shop.hideOwned"))}</label>
        </div>
        <p class="shop-result-count" role="status">${escapeHtml(t("shop.resultCount", { n: matches.length }))}</p>
        ${matches.length ? `<div class="shop-grid shop-results">${shown.map(renderShopTile).join("")}</div>` : `<div class="card shop-empty"><p>${escapeHtml(t("shop.empty"))}</p><button type="button" class="btn ghost" id="shop-clear-filters">${escapeHtml(t("shop.clearFilters"))}</button></div>`}
        ${matches.length > shown.length ? `<button type="button" class="btn ghost shop-more" id="shop-show-more">${escapeHtml(t("shop.showMore"))}</button>` : ""}
        ${secondaryLinks}${toastHtml}
      </section>`;
  }

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

  const contentShelves = bundlesHtml + shelvesHtml;
  const emptyHtml = `<p class="card center muted">${escapeHtml(t("shop.empty"))}</p>`;

  return `
    <section class="shop-shell">
      ${renderPreviewBar(state)}
      ${deliveryBanner}
      ${introHtml}
      ${tabsHtml}
      ${secondaryLinks}
      ${collectionsHtml}
      ${filtersHtml}
      ${shortcutsHtml}
      ${contentShelves || (collectionsHtml ? "" : emptyHtml)}
      ${toastHtml}
    </section>
  `;
}
