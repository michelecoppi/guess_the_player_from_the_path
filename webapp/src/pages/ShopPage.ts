import type { ShopController } from "@/features/shop/controller";
import type {
  ShopState,
  ShopSubview,
  ShopKindFilter,
  ShopPriceFilter,
} from "@/features/shop/types";
import { renderShopPage as renderShopPageView } from "@/features/shop/views";
import { t } from "@/i18n";

export function renderShopPage(state: ShopState): string {
  return renderShopPageView(state);
}

export function attachShopEventListeners(
  root: HTMLElement,
  controller: ShopController,
): void {
  // Subview switch tabs
  const tabButtons = root.querySelectorAll<HTMLButtonElement>("button[data-shop-view]");
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const view = btn.dataset.shopView as ShopSubview | undefined;
      if (view) {
        controller.setView(view);
      }
    });
  });

  // Filter dropdown: category / kind
  const kindSelect = root.querySelector<HTMLSelectElement>("#shop-kind");
  if (kindSelect) {
    kindSelect.addEventListener("change", () => {
      controller.setKindFilter(kindSelect.value as ShopKindFilter);
    });
  }

  // Filter dropdown: price ceiling
  const priceSelect = root.querySelector<HTMLSelectElement>("#shop-price");
  if (priceSelect) {
    priceSelect.addEventListener("change", () => {
      controller.setPriceFilter(priceSelect.value as ShopPriceFilter);
    });
  }

  // Filter checkbox: hide owned
  const hideOwnedCheckbox = root.querySelector<HTMLInputElement>("#shop-hide-owned");
  if (hideOwnedCheckbox) {
    hideOwnedCheckbox.addEventListener("change", () => {
      controller.setHideOwned(hideOwnedCheckbox.checked);
    });
  }

  // Try on / preview triggers
  const tryButtons = root.querySelectorAll<HTMLButtonElement>("button[data-try]");
  tryButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const id = btn.dataset.try;
      if (id) {
        controller.startPreview(id);
        window.scrollTo?.({ top: 0, behavior: "instant" as ScrollBehavior });
      }
    });
  });

  // Stop preview trigger
  const stopPreviewBtn = root.querySelector<HTMLButtonElement>("#shop-stop-preview");
  if (stopPreviewBtn) {
    stopPreviewBtn.addEventListener("click", (e) => {
      e.preventDefault();
      controller.stopPreview();
    });
  }

  // Equip triggers
  const equipButtons = root.querySelectorAll<HTMLButtonElement>("button[data-equip]");
  equipButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const id = btn.dataset.equip;
      if (id) {
        void controller.equip(id);
      }
    });
  });

  // Buy triggers (Telegram Stars)
  const buyButtons = root.querySelectorAll<HTMLButtonElement>("button[data-buy]");
  buyButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const id = btn.dataset.buy;
      if (id) {
        void controller.buy(id);
      }
    });
  });

  // Saved Look: save current look
  const saveLookBtn = root.querySelector<HTMLButtonElement>("#shop-save-look");
  if (saveLookBtn) {
    saveLookBtn.addEventListener("click", (e) => {
      e.preventDefault();
      const input = root.querySelector<HTMLInputElement>("#look-name");
      const name = input?.value || "";
      void controller.lookAction("save", name);
    });
  }

  // Saved Look: wear look
  const wearLookButtons = root.querySelectorAll<HTMLButtonElement>("button[data-use-look]");
  wearLookButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const name = btn.dataset.useLook;
      if (name) {
        void controller.lookAction("wear", name);
      }
    });
  });

  // Saved Look: delete look
  const deleteLookButtons = root.querySelectorAll<HTMLButtonElement>("button[data-delete-look]");
  deleteLookButtons.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const name = btn.dataset.deleteLook;
      if (name) {
        void controller.lookAction("delete", name);
      }
    });
  });

  // Retry catalogue load
  const retryBtn = root.querySelector<HTMLButtonElement>("#shop-retry");
  if (retryBtn) {
    retryBtn.addEventListener("click", (e) => {
      e.preventDefault();
      void controller.refresh();
    });
  }

  // Retry history load
  const historyRetryBtn = root.querySelector<HTMLButtonElement>("#shop-history-retry");
  if (historyRetryBtn) {
    historyRetryBtn.addEventListener("click", (e) => {
      e.preventDefault();
      void controller.loadHistory();
    });
  }

  // Copy support command
  const copyButtons = root.querySelectorAll<HTMLButtonElement>("button[data-copy-support]");
  copyButtons.forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      const index = btn.dataset.copySupport;
      const input = root.querySelector<HTMLTextAreaElement>(`#support-${index}`);
      if (input) {
        if (
          typeof navigator !== "undefined" &&
          navigator.clipboard &&
          typeof navigator.clipboard.writeText === "function"
        ) {
          try {
            await navigator.clipboard.writeText(input.value);
            controller.setToast(t("shop.copied"));
          } catch {
            input.focus();
            input.select();
          }
        } else {
          input.focus();
          input.select();
        }
      }
    });
  });
}
