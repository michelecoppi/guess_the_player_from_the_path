import { renderArenaPage as renderArenaView } from "@/features/arena/views";
import { renderTrainingView } from "@/features/training/views";
import type { ArenaState, ArenaSubview } from "@/features/arena/types";
import type { ArenaController } from "@/features/arena/controller";
import type { TrainingState } from "@/features/training/types";
import type { TrainingController } from "@/features/training/controller";

export type { ArenaSubview };

export interface ArenaPageOptions {
  subview?: ArenaSubview;
  arenaState?: ArenaState;
  trainingState?: TrainingState;
}

export function renderArenaPage(
  stateOrOptions?: ArenaState | ArenaPageOptions,
  maybeTrainingState?: TrainingState,
): string {
  if (!stateOrOptions) {
    return renderArenaView();
  }

  // Handle options object e.g. { subview: "training", trainingState }
  if ("trainingState" in stateOrOptions || ("subview" in stateOrOptions && !("status" in stateOrOptions))) {
    const opts = stateOrOptions as ArenaPageOptions;
    if (opts.subview === "training" && opts.trainingState) {
      return renderTrainingView(opts.trainingState);
    }
    const arenaState: ArenaState = opts.arenaState || {
      subview: opts.subview || "hub",
      status: "idle",
      busy: false,
      error: null,
      notice: null,
      confirming: null,
      data: null,
      activeDuelCode: null,
      invitationCode: null,
      searchQuery: "",
      searchResults: [],
      searchError: null,
      draftAnswer: "",
    };
    return renderArenaView(arenaState);
  }

  // It is ArenaState
  const arenaState = stateOrOptions as ArenaState;
  if (arenaState.subview === "training" && maybeTrainingState) {
    return renderTrainingView(maybeTrainingState);
  }
  return renderArenaView(arenaState);
}

export function attachArenaEventListeners(
  container: HTMLElement,
  arenaController?: ArenaController,
  trainingController?: TrainingController,
): void {
  // Navigation between Arena subviews (e.g. back to hub, open challenge, open training)
  container
    .querySelectorAll<HTMLButtonElement>("[data-arena-nav]")
    .forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        const subview = btn.dataset.arenaNav as ArenaSubview;
        if (subview) {
          arenaController?.setSubview(subview);
        }
      };
    });

  // Back from training view
  const backBtn =
    container.querySelector<HTMLButtonElement>("[data-training-back]");
  if (backBtn) {
    backBtn.onclick = (e) => {
      e.preventDefault();
      trainingController?.cancelConfirm();
      arenaController?.setSubview("hub");
    };
  }

  // Training controls
  const trainingStartBtn =
    container.querySelector<HTMLButtonElement>("#training-start");
  if (trainingStartBtn) {
    trainingStartBtn.onclick = (e) => {
      e.preventDefault();
      trainingController?.startNext();
    };
  }

  const trainingNextBtn =
    container.querySelector<HTMLButtonElement>("#training-next");
  if (trainingNextBtn) {
    trainingNextBtn.onclick = (e) => {
      e.preventDefault();
      trainingController?.startNext();
    };
  }

  const trainingRetryBtn =
    container.querySelector<HTMLButtonElement>("#training-retry");
  if (trainingRetryBtn) {
    trainingRetryBtn.onclick = (e) => {
      e.preventDefault();
      trainingController?.init();
    };
  }

  const trainingRevealBtn =
    container.querySelector<HTMLButtonElement>("#training-reveal");
  if (trainingRevealBtn) {
    trainingRevealBtn.onclick = (e) => {
      e.preventDefault();
      trainingController?.reveal();
    };
  }

  const trainingAnswerInput =
    container.querySelector<HTMLInputElement>("#training-answer");
  if (trainingAnswerInput) {
    trainingAnswerInput.oninput = () => {
      trainingController?.setDraftAnswer(trainingAnswerInput.value);
    };
    trainingAnswerInput.onkeydown = (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        trainingController?.submitGuess(trainingAnswerInput.value);
      }
    };
  }

  const trainingSearchForm =
    container.querySelector<HTMLFormElement>("form[role='search']");
  if (trainingSearchForm) {
    trainingSearchForm.onsubmit = (e) => {
      e.preventDefault();
      const val = trainingAnswerInput ? trainingAnswerInput.value : "";
      trainingController?.submitGuess(val);
    };
  }

  const trainingSubmitBtn =
    container.querySelector<HTMLButtonElement>("#training-submit");
  if (trainingSubmitBtn) {
    trainingSubmitBtn.onclick = (e) => {
      e.preventDefault();
      const val = trainingAnswerInput ? trainingAnswerInput.value : "";
      trainingController?.submitGuess(val);
    };
  }

  // Open an active or existing duel
  container
    .querySelectorAll<HTMLButtonElement>("[data-arena-duel]")
    .forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        const code = btn.dataset.arenaDuel;
        if (code && arenaController) {
          arenaController.loadDuel(code);
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
        if (code && arenaController) {
          arenaController.deleteDuel(code);
        }
      };
    });

  // Invite a searched opponent or friend via shareable duel link
  container
    .querySelectorAll<HTMLButtonElement>(
      "[data-arena-invite-user], [data-arena-challenge-user]",
    )
    .forEach((btn) => {
      btn.onclick = async (e) => {
        e.preventDefault();
        if (arenaController) {
          const duel = await arenaController.createNewDuel();
          if (duel?.invite_url) {
            arenaController.shareInvite(duel.invite_url);
          }
        }
      };
    });

  // Search input in challenge view
  const searchInput =
    container.querySelector<HTMLInputElement>("#opponent-search");
  if (searchInput && arenaController) {
    searchInput.oninput = () => {
      arenaController.searchOpponents(searchInput.value);
    };
  }

  // Direct create free duel button
  const createFreeDuelBtn = container.querySelector<HTMLButtonElement>(
    "#arena-create-free-duel",
  );
  if (createFreeDuelBtn && arenaController) {
    createFreeDuelBtn.onclick = (e) => {
      e.preventDefault();
      arenaController.createNewDuel();
    };
  }

  // Accept duel invitation button
  const acceptInviteBtn = container.querySelector<HTMLButtonElement>(
    "#arena-accept-invite",
  );
  if (acceptInviteBtn && arenaController) {
    acceptInviteBtn.onclick = (e) => {
      e.preventDefault();
      arenaController.acceptInvitation();
    };
  }

  // Create duel empty state button
  const createDuelBtn =
    container.querySelector<HTMLButtonElement>("#arena-create-duel");
  if (createDuelBtn && arenaController) {
    createDuelBtn.onclick = (e) => {
      e.preventDefault();
      arenaController.createNewDuel();
    };
  }

  // New duel finished state button
  const newDuelBtn =
    container.querySelector<HTMLButtonElement>("#arena-new-duel");
  if (newDuelBtn && arenaController) {
    newDuelBtn.onclick = (e) => {
      e.preventDefault();
      arenaController.createNewDuel();
    };
  }

  // Retry on error state button
  const retryBtn = container.querySelector<HTMLButtonElement>("#arena-retry");
  if (retryBtn && arenaController) {
    retryBtn.onclick = (e) => {
      e.preventDefault();
      const code = arenaController.getState().activeDuelCode;
      if (code) {
        arenaController.loadDuel(code);
      } else {
        arenaController.loadDuelList();
      }
    };
  }

  // Action buttons: invite, copy, skip, refresh
  container
    .querySelectorAll<HTMLButtonElement>("[data-arena-action]")
    .forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        if (!arenaController) return;
        const action = btn.dataset.arenaAction;
        switch (action) {
          case "invite":
            arenaController.shareInvite();
            break;
          case "copy":
            arenaController.copyInvite();
            break;
          case "skip":
            arenaController.skipRound();
            break;
          case "refresh": {
            const activeCode = arenaController.getState().activeDuelCode;
            if (activeCode) {
              arenaController.loadDuel(activeCode);
            } else {
              arenaController.loadDuelList();
            }
            break;
          }
        }
      };
    });

  // Guess input and form in duel view
  const answerInput =
    container.querySelector<HTMLInputElement>("#arena-answer");
  if (answerInput && arenaController) {
    answerInput.oninput = () => {
      arenaController.setDraftAnswer(answerInput.value);
    };
    answerInput.onkeydown = (event: KeyboardEvent) => {
      if (event.key === "Enter") {
        event.preventDefault();
        arenaController.submitGuess(answerInput.value);
      }
    };
  }

  const guessForm =
    container.querySelector<HTMLFormElement>("#arena-guess-form");
  if (guessForm && arenaController) {
    guessForm.onsubmit = (e) => {
      e.preventDefault();
      const input = container.querySelector<HTMLInputElement>("#arena-answer");
      const answer = input ? input.value : "";
      arenaController.submitGuess(answer);
    };
  }

  const submitBtn =
    container.querySelector<HTMLButtonElement>("#arena-submit");
  if (submitBtn && arenaController) {
    submitBtn.onclick = (e) => {
      e.preventDefault();
      const input = container.querySelector<HTMLInputElement>("#arena-answer");
      const answer = input ? input.value : "";
      arenaController.submitGuess(answer);
    };
  }
}
