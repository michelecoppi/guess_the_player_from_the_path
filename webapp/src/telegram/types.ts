/**
 * Telegram WebApp Types and Interfaces
 * Compatible with Telegram WebApp SDK v6.0+
 */

export interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
}

export interface TelegramThemeParams {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
  section_bg_color?: string;
}

export interface TelegramMainButton {
  text: string;
  color: string;
  textColor: string;
  isVisible: boolean;
  isActive: boolean;
  isProgressVisible: boolean;
  setText(text: string): TelegramMainButton;
  onClick(callback: () => void): TelegramMainButton;
  offClick(callback: () => void): TelegramMainButton;
  show(): TelegramMainButton;
  hide(): TelegramMainButton;
  enable(): TelegramMainButton;
  disable(): TelegramMainButton;
}

/** Native back arrow in the Mini App header (Bot API 6.1+). */
export interface TelegramBackButton {
  isVisible: boolean;
  show(): TelegramBackButton;
  hide(): TelegramBackButton;
  onClick(callback: () => void): TelegramBackButton;
  offClick(callback: () => void): TelegramBackButton;
}

export interface TelegramHapticFeedback {
  impactOccurred(style: "light" | "medium" | "heavy" | "rigid" | "soft"): TelegramHapticFeedback;
  notificationOccurred(type: "error" | "success" | "warning"): TelegramHapticFeedback;
  selectionChanged(): TelegramHapticFeedback;
}

export interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    query_id?: string;
    user?: TelegramUser;
    auth_date?: number;
    hash?: string;
    start_param?: string;
  };
  version: string;
  platform: string;
  colorScheme: "light" | "dark";
  themeParams: TelegramThemeParams;
  isExpanded: boolean;
  viewportHeight: number;
  viewportStableHeight: number;
  headerColor: string;
  backgroundColor: string;
  MainButton: TelegramMainButton;
  /** Missing on clients older than Bot API 6.1. */
  BackButton?: TelegramBackButton;
  HapticFeedback: TelegramHapticFeedback;
  safeAreaInset?: { top: number; bottom: number; left: number; right: number };
  contentSafeAreaInset?: { top: number; bottom: number; left: number; right: number };
  onEvent?(event: string, callback: () => void): void;
  offEvent?(event: string, callback: () => void): void;
  ready(): void;
  expand(): void;
  /** Missing on clients older than Bot API 6.1. */
  isVersionAtLeast?(version: string): boolean;
  /** Bot API 7.7+: vertical swipes no longer minimise/close the Mini App. */
  isVerticalSwipesEnabled?: boolean;
  disableVerticalSwipes?(): void;
  enableVerticalSwipes?(): void;
  /** Bot API 6.2+: ask before closing while a match is in progress. */
  isClosingConfirmationEnabled?: boolean;
  enableClosingConfirmation?(): void;
  disableClosingConfirmation?(): void;
  close(): void;
  openTelegramLink(url: string): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  openInvoice(url: string, callback?: (status: string) => void): void;
  switchInlineQuery(query: string, choose_chat_types?: string[]): void;
  /** Bot API 8.0+: shares a message the bot prepared (savePreparedInlineMessage). */
  shareMessage?(msgId: string, callback?: (sent: boolean) => void): void;
  /** Native alert popup (Bot API 6.2+). */
  showAlert?(message: string, callback?: () => void): void;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp: TelegramWebApp;
    };
  }
}
