import "./styles/foundation.css";
import "./styles/components.css";
import "./styles/features.css";
import "./styles/recap.css";
import "./styles/event-spotlight.css";
import "./styles/feature-overrides.css";
import "./styles/visual-polish.css";
import { bootstrap } from "./app/bootstrap";

if (typeof document !== "undefined") {
  // Windows renders flag emoji as two letters: the career hides them there (visual-polish.css).
  if (/Windows/.test(navigator.userAgent)) document.documentElement.classList.add("no-emoji-flags");
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      start();
    });
  } else {
    start();
  }
}

function start(): void {
  if (
    import.meta.env.DEV &&
    new URLSearchParams(location.search).has("design-review")
  ) {
    void import('./prototypes/review.css');
    void import("./prototypes/review").then(({ startReview }) =>
      startReview(document.getElementById("root")!),
    );
  } else bootstrap();
}
