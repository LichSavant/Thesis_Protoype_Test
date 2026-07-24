import type { EmailScanRecord, TrackedEmail } from "@phishing-defense/shared";

const API = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`);
  if (response.ok) return await response.json() as T;
  const payload = await response.json().catch(() => null) as { detail?: string | Array<{ msg?: string }> } | null;
  const detail = typeof payload?.detail === "string" ? payload.detail : Array.isArray(payload?.detail) ? payload.detail.map(item => item.msg).filter(Boolean).join("; ") : "";
  throw new Error(detail || `Backend request failed (${response.status}) at ${path}.`);
}

export async function getTrackedEmails(): Promise<TrackedEmail[]> {
  return getJson<TrackedEmail[]>("/api/v1/tracked-emails");
}

export async function getEmailScan(scanId: string): Promise<EmailScanRecord> {
  try { return await getJson<EmailScanRecord>(`/api/v1/email-scans/${encodeURIComponent(scanId)}`); }
  catch (error) { if (error instanceof Error && error.message === "Scan not found") throw new Error("The requested scan could not be found. It may have been deleted or the link may be invalid."); throw error; }
}

export async function getEmailScans(): Promise<EmailScanRecord[]> {
  return getJson<EmailScanRecord[]>("/api/v1/email-scans");
}
