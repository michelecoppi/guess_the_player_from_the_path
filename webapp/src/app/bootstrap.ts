import { App } from "./App";
import { getTelegramWebApp, isMockTelegramEnvironment } from "@/telegram/webapp";
import { reportStartup } from "@/telemetry/startup";
import { installErrorReporting } from "@/telemetry/errors";

export function bootstrap(): App | null {
  const root = document.getElementById("root");
  if (!root) {
    console.error("Root element #root not found in document.");
    return null;
  }

  // Only real Telegram sessions are measured and report errors: the dev mock has no signed
  // initData. Error reporting starts before the App so a crash during init is reported too.
  getTelegramWebApp();
  const measured = !isMockTelegramEnvironment();
  let app: App | null = null;
  if (measured) installErrorReporting({ screen: () => app?.getActiveTab() });

  app = new App(root);
  app.init();
  // Shop, Story and Events are separate chunks (#187): fetch them once the Daily is on screen
  // so opening them later is instant, without competing with the first load.
  const started = app;
  void started.whenFirstLoaded().finally(() => {
    setTimeout(() => void started.prefetchLazyViews(), 1000);
  });
  if (measured) {
    void started.whenFirstLoaded().then(
      () => reportStartup(started.getDailyController().getState().status === "error" ? "error" : "ok"),
      () => reportStartup("error"),
    );
  }
  return app;
}
