import type { EmailScanRecord, EmailSourceMetadata, ScanFeedbackRequest, TrackedEmail } from "@phishing-defense/shared";
export interface ExtensionResult { trackedEmail: TrackedEmail; analysis: EmailScanRecord; }
export type RuntimeMessage =
  | { type: "PROCESS_EMAIL"; email: EmailSourceMetadata }
  | { type: "PING_CONTENT_SCRIPT" }
  | { type: "GET_CURRENT_EMAIL" }
  | { type: "GET_LAST_RESULT" }
  | { type: "RECORD_SCAN_FEEDBACK"; feedback: ScanFeedbackRequest }
  | { type: "OPEN_SCAN_DASHBOARD"; scanId: string };
