import "./styles/foundation.css";
import "./styles/components.css";
import "./styles/features.css";
import "./styles/recap.css";
import "./styles/feature-overrides.css";
import { bootstrap } from "./app/bootstrap";

if (typeof document !== "undefined") {
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
