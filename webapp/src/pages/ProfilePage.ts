import { renderPrototype } from "@/prototypes/screens";
import type { TelegramUser } from "@/telegram/types";
export interface ProfilePageProps {
  user?: TelegramUser | null;
}
export function renderProfilePage(_props: ProfilePageProps = {}): string {
  return renderPrototype("profile");
}
