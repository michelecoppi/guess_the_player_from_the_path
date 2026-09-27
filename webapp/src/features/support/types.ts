export interface SupportReportState {
  status: "idle" | "sending" | "sent" | "error";
  /** Last submitted text: kept on failure so a retry doesn't mean retyping it. */
  draft: string;
}
