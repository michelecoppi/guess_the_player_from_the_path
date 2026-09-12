import { renderArenaPage as renderArenaView } from "@/features/arena/views";
import type { ArenaState, ArenaSubview } from "@/features/arena/types";
import type { ArenaController } from "@/features/arena/controller";

export function renderArenaPage(state?: ArenaState): string {
  return renderArenaView(state);
}

export function attachArenaEventListeners(
  container: HTMLElement,
  controller: ArenaController,
): void {
  // Navigation between Arena subviews (e.g. back to hub, open challenge)
  container
    .querySelectorAll<HTMLButtonElement>("[data-arena-nav]")
    .forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        const subview = btn.dataset.arenaNav as ArenaSubview;
        if (subview) {
          controller.setSubview(subview);
        }
      };
    });

  // Open an active or existing duel
  container
    .querySelectorAll<HTMLButtonElement>("[data-arena-duel]")
    .forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        const code = btn.dataset.arenaDuel;
        if (code) {
          controller.loadDuel(code);
        }
      };
    });

  // Delete an unjoined duel
  container
    .querySelectorAll<HTMLButtonElement>("[data-arena-delete]")
    .forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        const code = btn.dataset.arenaDelete;
        if (code) {
          controller.deleteDuel(code);
        }
      };
    });

  // Challenge a specific searched opponent
  container
    .querySelectorAll<HTMLButtonElement>("[data-arena-challenge-user]")
    .forEach((btn) => {
      btn.onclick = async (e) => {
        e.preventDefault();
        const duel = await controller.createNewDuel();
        if (duel?.invite_url) {
          controller.shareInvite(duel.invite_url);
        }
      };
    });

  // Search input in challenge view
  const searchInput =
    container.querySelector<HTMLInputElement>("#opponent-search");
  if (searchInput) {
    searchInput.oninput = () => {
      controller.searchOpponents(searchInput.value);
    };
  }

  // Direct create free duel button
  const createFreeDuelBtn = container.querySelector<HTMLButtonElement>(
    "#arena-create-free-duel",
  );
  if (createFreeDuelBtn) {
    createFreeDuelBtn.onclick = (e) => {
      e.preventDefault();
      controller.createNewDuel();
    };
  }

  // Accept duel invitation button
  const acceptInviteBtn = container.querySelector<HTMLButtonElement>(
    "#arena-accept-invite",
  );
  if (acceptInviteBtn) {
    acceptInviteBtn.onclick = (e) => {
      e.preventDefault();
      controller.acceptInvitation();
    };
  }

  // Create duel empty state button
  const createDuelBtn =
    container.querySelector<HTMLButtonElement>("#arena-create-duel");
  if (createDuelBtn) {
    createDuelBtn.onclick = (e) => {
      e.preventDefault();
      controller.createNewDuel();
    };
  }

  // New duel finished state button
  const newDuelBtn =
    container.querySelector<HTMLButtonElement>("#arena-new-duel");
  if (newDuelBtn) {
    newDuelBtn.onclick = (e) => {
      e.preventDefault();
      controller.createNewDuel();
    };
  }

  // Retry on error state button
  const retryBtn = container.querySelector<HTMLButtonElement>("#arena-retry");
  if (retryBtn) {
    retryBtn.onclick = (e) => {
      e.preventDefault();
      const code = controller.getState().activeDuelCode;
      if (code) {
        controller.loadDuel(code);
      } else {
        controller.loadDuelList();
      }
    };
  }

  // Action buttons: invite, copy, skip, refresh
  container
    .querySelectorAll<HTMLButtonElement>("[data-arena-action]")
    .forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        const action = btn.dataset.arenaAction;
        switch (action) {
          case "invite":
            controller.shareInvite();
            break;
          case "copy":
            controller.copyInvite();
            break;
          case "skip":
            controller.skipRound();
            break;
          case "refresh": {
            const activeCode = controller.getState().activeDuelCode;
            if (activeCode) {
              controller.loadDuel(activeCode);
            } else {
              controller.loadDuelList();
            }
            break;
          }
        }
      };
    });

  // Guess input and form in duel view
  const answerInput =
    container.querySelector<HTMLInputElement>("#arena-answer");
  if (answerInput) {
    answerInput.oninput = () => {
      controller.setDraftAnswer(answerInput.value);
    };
    answerInput.onkeydown = (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        controller.submitGuess(answerInput.value);
      }
    };
  }

  const guessForm =
    container.querySelector<HTMLFormElement>("#arena-guess-form");
  if (guessForm) {
    guessForm.onsubmit = (e) => {
      e.preventDefault();
      const input = container.querySelector<HTMLInputElement>("#arena-answer");
      const answer = input ? input.value : "";
      controller.submitGuess(answer);
    };
  }

  const submitBtn =
    container.querySelector<HTMLButtonElement>("#arena-submit");
  if (submitBtn) {
    submitBtn.onclick = (e) => {
      e.preventDefault();
      const input = container.querySelector<HTMLInputElement>("#arena-answer");
      const answer = input ? input.value : "";
      controller.submitGuess(answer);
    };
  }
}
