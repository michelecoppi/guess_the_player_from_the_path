import type { NavTabId } from "@/components/NavBar";
type AuxiliaryTab = "reports" | "refunds" | "privacy";

type PageFactories = Record<Exclude<NavTabId, AuxiliaryTab>, () => string> & {
  fallback: (tab: AuxiliaryTab) => string;
};

/** Invoke only the active page factory; inactive views are never rendered. */
export function renderActivePage(tab: NavTabId, pages: PageFactories): string {
  if (tab === "reports" || tab === "refunds" || tab === "privacy") {
    return pages.fallback(tab);
  }
  return pages[tab]();
}
