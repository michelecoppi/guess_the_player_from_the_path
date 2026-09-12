/** Explicit DEV-only visual harness: no controller, auth or fetch. */
import { renderHeader } from "@/components/Header";
import { renderNavBar, type NavTabId } from "@/components/NavBar";
import { renderDailyPage } from "@/pages/DailyPage";
import { renderPrototype } from "./screens";
import {
  dailyFixture,
  REVIEW_STATES,
  type ReviewState,
} from "./daily-fixtures";
import { setLanguage } from "@/i18n";
export function startReview(root: HTMLElement): void {
  let page: NavTabId = "play";
  let state: ReviewState = "ready";
  let theme = "light";
  setLanguage("it");
  function render() {
    document.documentElement.dataset.theme = theme;
    root.innerHTML = `${renderHeader({ user: { id: 1, first_name: "Marco" }, activeTab: page })}<div class="review-controls"><b>DESIGN REVIEW</b><label>State <select id="review-state">${REVIEW_STATES.map((s) => `<option ${s === state ? "selected" : ""}>${s}</option>`).join("")}</select></label><label>Theme <select id="review-theme"><option ${theme === "light" ? "selected" : ""}>light</option><option ${theme === "dark" ? "selected" : ""}>dark</option></select></label></div><main id="app-content">${page === "play" ? renderDailyPage(dailyFixture(state)) : renderPrototype(page)}</main>${renderNavBar({ activeTab: page })}`;
    root.querySelectorAll<HTMLButtonElement>("[data-tab]").forEach(
      (btn) =>
        (btn.onclick = () => {
          page = btn.dataset.tab as NavTabId;
          render();
        }),
    );
    root.querySelector<HTMLSelectElement>("#review-state")!.onchange = (
      event,
    ) => {
      state = (event.target as HTMLSelectElement).value as ReviewState;
      page = "play";
      render();
    };
    root.querySelector<HTMLSelectElement>("#review-theme")!.onchange = (
      event,
    ) => {
      theme = (event.target as HTMLSelectElement).value;
      render();
    };
    const submit = root.querySelector<HTMLButtonElement>("#submit");
    if (submit)
      submit.onclick = () => {
        state = "wrong";
        render();
      };
    const hint = root.querySelector<HTMLButtonElement>("#hint");
    if (hint)
      hint.onclick = () => {
        state = "hint";
        render();
      };
    const retry = root.querySelector<HTMLButtonElement>("#daily-retry");
    if (retry)
      retry.onclick = () => {
        state = "ready";
        render();
      };
  }
  render();
}
