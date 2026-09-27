import { App } from "./App";
import { isMockTelegramEnvironment } from "@/telegram/webapp";
import { reportStartup } from "@/telemetry/startup";

export function bootstrap(): App | null {
  const root = document.getElementById("root");
  if (!root) {
    console.error("Root element #root not found in document.");
    return null;
  }

  const app = new App(root);
  app.init();
  // Only real Telegram sessions are measured: the dev mock has no signed initData.
  if (!isMockTelegramEnvironment()) {
    void app.whenFirstLoaded().then(
      () => reportStartup(app.getDailyController().getState().status === "error" ? "error" : "ok"),
      () => reportStartup("error"),
    );
  }
  return app;
}
