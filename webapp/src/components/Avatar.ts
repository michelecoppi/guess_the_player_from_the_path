import { escapeHtml, initials } from "@/utils/format";

export interface AvatarProps {
  id?: string;
  name?: string;
  initialsText?: string;
  photoUrl?: string;
  size?: "small" | "normal" | "large";
  ringStyle?: string;
  spinRing?: boolean;
  tactics?: 3 | 11;
  extraClass?: string;
}

export function renderAvatar(props: AvatarProps): string {
  const size = props.size || "normal";
  const sizeClass = size === "small" ? "small" : size === "large" ? "large" : "";
  const initial = props.initialsText || initials(props.name);

  let ringHtml = "";
  if (props.ringStyle) {
    const spinClass = props.spinRing ? " spin" : "";
    ringHtml = `<div class="ring${spinClass}" style="${escapeHtml(props.ringStyle)}" aria-hidden="true"></div>`;
  }

  const nodes = props.tactics === 3 || props.tactics === 11 ? props.tactics : 0;
  const tactics = nodes ? `<svg class="avatar-tactics" viewBox="0 0 100 100" aria-hidden="true">${Array.from({length:nodes}, (_,i) => {
    const angle = (i / nodes * 2 * Math.PI) - Math.PI / 2;
    return `<circle cx="${50 + 46 * Math.cos(angle)}" cy="${50 + 46 * Math.sin(angle)}" r="3"/>`;
  }).join('')}<circle class="tactics-ball" cx="50" cy="4" r="2.5"/></svg>` : '';

  const avatarContent = props.photoUrl
    ? `<img src="${escapeHtml(props.photoUrl)}" alt="${escapeHtml(props.name || "Avatar")}" loading="lazy" />`
    : `<span>${escapeHtml(initial)}</span>`;

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
