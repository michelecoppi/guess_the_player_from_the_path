import type { TelegramWebApp, TelegramUser } from "./types";

export const DEFAULT_MOCK_USER: TelegramUser = {
  id: 42,
  first_name: "Marco",
  last_name: "Rossi",
  username: "marcorossi",
  language_code: "it",
  is_premium: false,
};

export function createMockTelegramWebApp(user: TelegramUser = DEFAULT_MOCK_USER): TelegramWebApp {
  const mainButton = {
    text: "CONTINUA",
    color: "#38bd82",
    textColor: "#0a1a12",
    isVisible: false,
    isActive: true,
    isProgressVisible: false,
    setText(text: string) {
      this.text = text;
      return this;
    },
    onClick(_cb: () => void) {
      return this;
    },
    offClick(_cb: () => void) {
      return this;
    },
    show() {
      this.isVisible = true;
      return this;
    },
    hide() {
      this.isVisible = false;
      return this;
    },
    enable() {
      this.isActive = true;
      return this;
    },
    disable() {
      this.isActive = false;
      return this;
    },
  };

  const hapticFeedback = {
    impactOccurred(_style: "light" | "medium" | "heavy" | "rigid" | "soft") {
      return this;
    },
    notificationOccurred(_type: "error" | "success" | "warning") {
      return this;
    },
    selectionChanged() {
      return this;
    },
  };

  return {
    initData: "mock_init_data_for_dev=true&user_id=42",
    initDataUnsafe: {
      user,
      auth_date: Math.floor(Date.now() / 1000),
      hash: "mock_hash",
    },
    version: "6.9",
    platform: "dev_browser",
    colorScheme: "dark",
    themeParams: {
      bg_color: "#0a131e",
      secondary_bg_color: "#132437",
      section_bg_color: "#1a2c40",
      text_color: "#ecf2f8",
      hint_color: "#8ea2b6",
      button_color: "#38bd82",
      button_text_color: "#0a1a12",
    },
    isExpanded: true,
    viewportHeight: 600,
    viewportStableHeight: 600,
    headerColor: "#0a131e",
    backgroundColor: "#0a131e",
    MainButton: mainButton,
    HapticFeedback: hapticFeedback,
    ready() {},
    expand() {},
    close() {
      console.log("[Telegram Mock] close() called");
    },
    openTelegramLink(url: string) {
      window.open(url, "_blank", "noopener");
    },
    openLink(url: string) {
      window.open(url, "_blank", "noopener");
    },
    openInvoice(_url: string, callback?: (status: string) => void) {
      if (callback) callback("paid");
    },
    switchInlineQuery(query: string) {
      console.log(`[Telegram Mock] switchInlineQuery: ${query}`);
    },
  };
}
