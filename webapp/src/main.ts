import "./styles/vars.css";
import "./styles/app.css";
import { bootstrap } from "./app/bootstrap";

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      bootstrap();
    });
  } else {
    bootstrap();
  }
}
