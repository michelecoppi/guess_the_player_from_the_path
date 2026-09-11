import { App } from "./App";

export function bootstrap(): App | null {
  const root = document.getElementById("root");
  if (!root) {
    console.error("Root element #root not found in document.");
    return null;
  }

  const app = new App(root);
  app.init();
  return app;
}
