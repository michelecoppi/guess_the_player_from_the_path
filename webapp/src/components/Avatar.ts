import { escapeHtml, initials } from "@/utils/format";

export interface AvatarProps {
  id?: string;
  name?: string;
  initialsText?: string;
  photoUrl?: string;
  size?: "small" | "normal" | "large";
  ringStyle?: string;
  spinRing?: boolean;
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

  const avatarContent = props.photoUrl
    ? `<img src="${escapeHtml(props.photoUrl)}" alt="${escapeHtml(props.name || "Avatar")}" loading="lazy" />`
    : `<span>${escapeHtml(initial)}</span>`;

  const idAttr = props.id ? ` id="${escapeHtml(props.id)}"` : "";
  const classAttr = `avatar-wrap ${sizeClass} ${props.extraClass || ""}`.trim();

  return `
    <div class="${classAttr}"${idAttr} aria-label="${escapeHtml(props.name || "User avatar")}">
      ${ringHtml}
      <div class="avatar">
        ${avatarContent}
      </div>
    </div>
  `.trim();
}
