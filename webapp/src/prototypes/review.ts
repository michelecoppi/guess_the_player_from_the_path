import { appearanceFixtures, type AppearanceFixtureName } from "./appearance-fixtures";
import { applyResolvedAppearance, appearanceSquares } from "@/appearance";
import { renderAppearanceIdentity } from "@/appearance/surfaces";
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
  let outfit: AppearanceFixtureName = "default";
  setLanguage("it");
  function render() {
    document.documentElement.dataset.theme = "dark";
    const appearance = applyResolvedAppearance(appearanceFixtures[outfit]);
    const daily = dailyFixture(state);
    daily.squaresSymbols = appearanceSquares(appearance);
    root.innerHTML = `${renderHeader({ user: { id: 1, first_name: "Marco" }, activeTab: page })}<div class="review-controls"><b>DESIGN REVIEW</b><label>State <select id="review-state">${REVIEW_STATES.map((s) => `<option ${s === state ? "selected" : ""}>${s}</option>`).join("")}</select></label><label>Appearance <select id="review-appearance">${Object.keys(appearanceFixtures).map((name) => `<option ${name === outfit ? "selected" : ""}>${name}</option>`).join("")}</select></label></div><div class="appearance-preview">${renderAppearanceIdentity("Marco", appearance)}</div><main id="app-content">${page === "play" ? renderDailyPage(daily) : renderPrototype(page)}</main>${renderNavBar({ activeTab: page })}`;
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
    root.querySelector<HTMLSelectElement>("#review-appearance")!.onchange = (
      event,
    ) => {
      outfit = (event.target as HTMLSelectElement).value as AppearanceFixtureName;
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
