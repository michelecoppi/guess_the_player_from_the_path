import { api, type ApiClient } from "@/api/client";

/**
 * Sends a bug/data report to the admins via POST /app/api/support/report.
 * Same channel as /paysupport in chat, but for the mini app menu's "Segnalazioni" screen.
 */
export async function sendReport(
  message: string,
  client: ApiClient = api,
): Promise<{ status: string }> {
  return client.post<{ status: string }>("/support/report", { message });
}
