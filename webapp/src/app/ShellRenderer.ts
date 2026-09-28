import { renderHeader, type HeaderProps } from "@/components/Header";
import { renderNavBar, type NavTabId } from "@/components/NavBar";
import { v } from "@/i18n/visual";

/** Keeps the application shell mounted while replacing the current page. */
export function renderScreen(
  root: HTMLElement,
  tab: NavTabId,
  user: HeaderProps["user"],
  mockBannerHtml: string,
  pageHtml: string,
): void {
  const main = root.querySelector<HTMLElement>("#app-content");
  if (!main) {
    root.innerHTML = `
      ${renderHeader({ user, activeTab: tab })}
      ${mockBannerHtml}
      <main id="app-content" role="region" aria-label="${v("pageContent")}">
        ${pageHtml}
      </main>
      ${renderNavBar({ activeTab: tab })}
    `;
    root.dataset.activeTab = tab;
    return;
  }

  if (root.dataset.activeTab !== tab) {
    const header = root.querySelector(".app-header");
    if (header) header.outerHTML = renderHeader({ user, activeTab: tab });
    const nav = root.querySelector(".app-nav");
    if (nav) nav.outerHTML = renderNavBar({ activeTab: tab });
    root.dataset.activeTab = tab;
  }
  main.innerHTML = pageHtml;
}
