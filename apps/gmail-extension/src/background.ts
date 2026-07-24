import type { EmailSourceMetadata } from "@phishing-defense/shared";
import type { ExtensionResult, RuntimeMessage } from "./messages";
import { processEmail, recordScanFeedback } from "./services/api";
import { loadSettings } from "./services/settings";

let lastResult: ExtensionResult | null = null;

chrome.runtime.onMessage.addListener((message: RuntimeMessage, _sender, sendResponse) => {
  if (message.type === "GET_LAST_RESULT") { sendResponse({ ok: true, result: lastResult }); return false; }
  if (message.type === "OPEN_SCAN_DASHBOARD") {
    void chrome.tabs.create({ url: `http://localhost:5173/?scanId=${encodeURIComponent(message.scanId)}` });
    sendResponse({ ok: true }); return false;
  }
  if (message.type === "RECORD_SCAN_FEEDBACK") {
    void loadSettings().then((settings) => recordScanFeedback(settings.backendUrl, message.feedback))
      .then(() => sendResponse({ ok: true })).catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Feedback failed" }));
    return true;
  }
  if (message.type !== "PROCESS_EMAIL") return false;
  void handleEmail(message.email).then((result) => sendResponse({ ok: true, result })).catch((error) =>
    sendResponse({ ok: false, error: error instanceof Error ? error.message : "Analysis failed" }));
  return true;
});

async function handleEmail(email: EmailSourceMetadata): Promise<ExtensionResult> {
  const settings = await loadSettings();
  lastResult = await processEmail(settings.backendUrl, email);
  await chrome.storage.local.set({ lastResult });
  return lastResult;
}
