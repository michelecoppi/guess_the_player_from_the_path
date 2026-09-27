import { escapeHtml } from "@/utils/format";
import { icon } from "@/components/Icon";
import { v } from "@/i18n/visual";
import { t } from "@/i18n";
import { renderLoadingState } from "@/components/LoadingState";
import { renderErrorState } from "@/components/ErrorState";
import type { NavTabId } from "@/components/NavBar";
import {
  type ReferralState,
  type ReferralController,
  renderReferralView,
  renderRewardReveal,
  watchReferralMotion,
} from "@/features/referral";

export function renderReferralPage(
  state: ReferralState,
  selectedMilestone = state.selectedRewardTarget !== null && state.data?.rewards
    ? state.data.rewards.find((r) => r.target === state.selectedRewardTarget) || null
    : null,
): string {
  const backBtn = `
    <button type="button" class="back-link" data-tab="profile" aria-label="${escapeHtml(v("backProfile"))}">
      ${icon("back")}${escapeHtml(v("backProfile"))}
    </button>
  `;

  const toastHtml = state.toast
    ? `<div class="toast rf-toast" role="status" aria-live="polite">${escapeHtml(state.toast)}</div>`
    : "";

  if (state.status === "loading" && !state.data) {
    return `
      ${backBtn}
      ${renderLoadingState({ message: t("common.loading") })}
    `;
  }

  if (state.status === "error" && !state.data) {
    return `
      ${backBtn}
      <div class="card" role="status">
        ${renderErrorState({
          message: state.errorNotice || t("referral.unavailable"),
          retryLabel: t("referral.retry"),
          retryButtonId: "rf-retry",
        })}
      </div>
    `;
  }

  let contentHtml = "";

  if (state.selectedRewardTarget !== null) {
    contentHtml = renderRewardReveal(
      state.selectedRewardTarget,
      selectedMilestone,
      state.data?.qualified || 0,
      state.equippingItemId,
    );
  } else {
    contentHtml = renderReferralView(state);
  }

  return `
    ${toastHtml}
    ${backBtn}
    <div class="referral-page-shell">
      ${contentHtml}
    </div>
  `;
}

export function attachReferralEventListeners(
  root: HTMLElement,
  controller: ReferralController,
  onNavigate?: (tab: NavTabId) => void,
): void {
  watchReferralMotion(root);

  // Back to profile navigation
  root.querySelectorAll<HTMLElement>(".back-link[data-tab]").forEach((btn) => {
    btn.onclick = (e) => {
      e.preventDefault();
      const tab = btn.dataset.tab as NavTabId;
      if (tab) {
        onNavigate ? onNavigate(tab) : window.history?.back?.();
      }
    };
  });

  // Retry on first load failure
  const retryBtn = root.querySelector<HTMLButtonElement>("#rf-retry");
  if (retryBtn) {
    retryBtn.onclick = () => {
      void controller.init(true);
    };
  }

  // Manual refresh
  const refreshBtn = root.querySelector<HTMLButtonElement>("#rf-refresh");
  if (refreshBtn) {
    refreshBtn.onclick = () => {
      void controller.refresh();
    };
  }

  // Load more friends
  const moreBtn = root.querySelector<HTMLButtonElement>("#rf-more");
  if (moreBtn) {
    moreBtn.onclick = () => {
      void controller.loadMore();
    };
  }

  // Invite share CTA
  const inviteBtn = root.querySelector<HTMLButtonElement>("#rf-invite");
  if (inviteBtn) {
    inviteBtn.onclick = () => {
      controller.shareInvite();
    };
  }

  // Copy link
  const copyBtn = root.querySelector<HTMLButtonElement>("#rf-copy");
  if (copyBtn) {
    copyBtn.onclick = () => {
      void controller.copyLink();
    };
  }

  // Milestone reward preview open
  root.querySelectorAll<HTMLElement>("[data-rf-preview]").forEach((el) => {
    el.onclick = () => {
      const target = Number(el.dataset.rfPreview);
      if (!isNaN(target)) {
        controller.openRewardPreview(target);
        window.scrollTo?.({ top: 0, behavior: "smooth" });
      }
    };
  });

  // Milestone reward preview close
  const closePreviewBtn = root.querySelector<HTMLButtonElement>("#rf-close-preview");
  if (closePreviewBtn) {
    closePreviewBtn.onclick = () => {
      controller.closeRewardPreview();
    };
  }

  // Equip unlocked cosmetic
  root.querySelectorAll<HTMLButtonElement>("[data-rf-equip]").forEach((btn) => {
    btn.onclick = () => {
      const itemId = btn.dataset.rfEquip;
      if (itemId) {
        btn.disabled = true;
        void controller.equipItem(itemId);
      }
    };
  });
}
