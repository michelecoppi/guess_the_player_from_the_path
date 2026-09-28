import type { NavTabId } from "@/components/NavBar";

/** Navigation state is independent of the DOM and feature controllers. */
export class Router {
  private tab: NavTabId = "play";
  private history: NavTabId[] = [];

  get activeTab(): NavTabId {
    return this.tab;
  }

  get visitedTabs(): readonly NavTabId[] {
    return [...this.history];
  }

  navigate(tab: NavTabId): boolean {
    if (this.tab === tab) return false;
    this.history.push(this.tab);
    if (this.history.length > 32) this.history.shift();
    this.tab = tab;
    return true;
  }

  static isArenaTab(tab: NavTabId): boolean {
    return tab === "arena" || tab === "duels" || tab === "challenge";
  }
}
