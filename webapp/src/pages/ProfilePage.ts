import type { ProfileController } from "@/features/profile/controller";
import type { CabinetFilter, ProfileState } from "@/features/profile/types";
import { renderProfileView } from "@/features/profile/views";

export function renderProfilePage(state: ProfileState): string {
  return renderProfileView(state);
}

export function attachProfileEventListeners(
  root: HTMLElement,
  controller: ProfileController,
): void {
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

  // Retry profile load button
  const retryBtn = root.querySelector<HTMLButtonElement>("#profile-retry-btn");
  retryBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    void controller.refresh();
  });
}
