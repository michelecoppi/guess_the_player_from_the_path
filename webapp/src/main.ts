import "./styles/vars.css";
import "./styles/app.css";
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
    void import("./prototypes/review").then(({ startReview }) =>
      startReview(document.getElementById("root")!),
    );
  } else bootstrap();
}
