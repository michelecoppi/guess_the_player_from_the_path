import { escapeHtml, initials } from "@/utils/format";
import { FRAME_MOTIONS } from "@/appearance/decorations";

/** Same path as services/avatars.py AVATAR_PATH. */
export const AVATAR_PATH = "/app/api/avatar/";

/**
 * A photo that fails to load (no photo, hidden by privacy, Telegram down) removes itself and
 * the initials underneath show. One capturing listener for the whole document: `error` does
 * not bubble, and inline handlers are not used anywhere in the app.
 */
export function bindAvatarPhotos(root: Document | HTMLElement): void {
  root.addEventListener("error", (event) => {
    const target = event.target as Element | null;
    if (target?.tagName === "IMG" && target.classList.contains("avatar-photo")) target.remove();
  }, true);
}

export interface AvatarProps {
  id?: string;
  name?: string;
  initialsText?: string;
  photoUrl?: string;
  size?: "small" | "normal" | "large";
  ringStyle?: string;
  spinRing?: boolean;
  tactics?: 3 | 11;
  /** Reviewed bounded flourish (FRAME_MOTIONS); anything else is ignored. */
  ringMotion?: string;
  extraClass?: string;
}

export function renderAvatar(props: AvatarProps): string {
  const size = props.size || "normal";
  const sizeClass = size === "small" ? "small" : size === "large" ? "large" : "";
  const initial = props.initialsText || initials(props.name);

  let ringHtml = "";
  if (props.ringStyle) {
    const spinClass = props.spinRing ? " spin" : "";
    const motion = props.ringMotion && FRAME_MOTIONS.has(props.ringMotion) ? ` data-motion="${props.ringMotion}"` : "";
    ringHtml = `<div class="ring${spinClass}"${motion} style="${escapeHtml(props.ringStyle)}" aria-hidden="true"></div>`;
  }

  const nodes = props.tactics === 3 || props.tactics === 11 ? props.tactics : 0;
  const tactics = nodes ? `<svg class="avatar-tactics" viewBox="0 0 100 100" aria-hidden="true">${Array.from({length:nodes}, (_,i) => {
    const angle = (i / nodes * 2 * Math.PI) - Math.PI / 2;
    return `<circle cx="${50 + 46 * Math.cos(angle)}" cy="${50 + 46 * Math.sin(angle)}" r="3"/>`;
  }).join('')}<circle class="tactics-ball" cx="50" cy="4" r="2.5"/></svg>` : '';

  // The initials are always there; the Telegram photo (#296) lies on top once it loads and
  // removes itself if it does not (bindAvatarPhotos), so a missing photo leaves the initials.
  // Only our own signed avatar path is accepted: the URL comes from the server payload.
  const photo = props.photoUrl && props.photoUrl.startsWith(AVATAR_PATH) ? props.photoUrl : "";
  const avatarContent = `<span>${escapeHtml(initial)}</span>${photo
    ? `<img class="avatar-photo" src="${escapeHtml(photo)}" alt="" loading="lazy" decoding="async" />`
    : ""}`;

  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `avatar-wrap ${sizeClass} ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr} aria-label="${escapeHtml(props.name || "User avatar")}">
      ${ringHtml}
      ${tactics}
      <div class="avatar">
        ${avatarContent}
      </div>
    </div>
  `.trim();
}
