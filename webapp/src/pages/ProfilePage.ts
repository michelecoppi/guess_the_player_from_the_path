import type { ProfileController } from "@/features/profile/controller";
import type { CabinetFilter, ProfileState } from "@/features/profile/types";
import { renderProfileView, setHeatmapOpen } from "@/features/profile/views";
import { bindRecapEntries } from "@/features/recap/entry";

export function renderProfilePage(state: ProfileState): string {
  return renderProfileView(state);
}

export function attachProfileEventListeners(
  root: HTMLElement,
  controller: ProfileController,
): void {
  bindRecapEntries(root);

  // Open cabinet button
  const openCabinetBtn = root.querySelector<HTMLButtonElement>("#open-cabinet");
  openCabinetBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    controller.openCabinet();
  });

  // Close cabinet / back button
  const closeCabinetBtn = root.querySelector<HTMLButtonElement>("#close-cabinet");
  closeCabinetBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    controller.closeCabinet();
  });

  // Cabinet filter buttons
  const filterButtons = root.querySelectorAll<HTMLButtonElement>(
    "button[data-cabinet-filter]",
  );
  filterButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const filter = btn.dataset.cabinetFilter as CabinetFilter | undefined;
      if (filter) {
        controller.setCabinetFilter(filter);
      }
    });
  });

  // Trophy pin toggle buttons
  const pinButtons = root.querySelectorAll<HTMLButtonElement>("button[data-pin]");
  pinButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const code = btn.dataset.pin;
      if (code) {
        void controller.togglePin(code);
      }
    });
  });

  const heatmap = root.querySelector<HTMLDetailsElement>("details.heatmap-card");
  // Recorded on the click itself, not on "toggle": that event is async and is lost when a
  // re-render (a profile refresh) replaces the element right after the tap.
  heatmap?.querySelector("summary")?.addEventListener("click", () => {
    const opening = !heatmap.open;
    // The first opening shows the squares for the first time: let them pop in.
    if (setHeatmapOpen(opening) && opening) heatmap.querySelector(".heatmap")?.classList.add("intro");
  });

  root.querySelectorAll<HTMLButtonElement>("button[data-heat-day]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      if (btn.dataset.heatDay) controller.selectHeatmapDay(btn.dataset.heatDay);
    });
  });

  // Retry profile load button
  const retryBtn = root.querySelector<HTMLButtonElement>("#profile-retry-btn");
  retryBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    void controller.refresh();
  });
}
