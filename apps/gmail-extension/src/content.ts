import { GmailEmailSourceAdapter } from "./adapters/gmailEmailSourceAdapter";
import { EmailSourceUnavailableError } from "./adapters/emailSourceAdapter";
import type { RuntimeMessage } from "./messages";
import { loadSettings } from "./services/settings";
import { AutoTrackingGuard } from "./services/autoTrackingGuard";
import { GMAIL_SELECTORS } from "./adapters/gmailSelectors";
import type { ExtensionResult } from "./messages";
import { normalizeBehaviorLabel, riskCategoryFromScore, riskCategoryLabel } from "@phishing-defense/shared";
import { ensureScanButton, SCAN_BUTTON_ID } from "./services/gmailScanButton";

const trackingGuard = new AutoTrackingGuard();
let debounceTimer: number | undefined;
let activeMessageId: string | null = null;
let scanning = false;

const UI = { button: SCAN_BUTTON_ID, popup: "sentinel-scan-popup", style: "sentinel-scan-style" } as const;

async function extractCurrent() {
  const settings = await loadSettings();
  return new GmailEmailSourceAdapter(document, { includeLinks: settings.includeLinks }).extractCurrentEmail();
}

async function extractForScan() {
  return new GmailEmailSourceAdapter(document, { includeLinks: true, includeBody: true, bodyAuthorized: true }).extractCurrentEmail();
}

function addStyles(): void {
  if (document.getElementById(UI.style)) return;
  const style = document.createElement("style"); style.id = UI.style;
  style.textContent = `#${UI.button}{display:inline-flex;align-items:center;gap:8px;height:36px;padding:0 16px;border:1px solid #dadce0;border-radius:18px;background:#fff;color:#3c4043;font:500 14px Arial,sans-serif;cursor:pointer;margin:0 4px}#${UI.button}:hover{background:#f6f8fc;box-shadow:0 1px 2px rgba(60,64,67,.15)}#${UI.button}:focus-visible{outline:2px solid #1a73e8;outline-offset:2px}#${UI.button}[disabled]{opacity:.6;cursor:default}#${UI.button} svg{width:18px;height:18px}#${UI.popup}{position:fixed;z-index:2147483646;right:24px;bottom:24px;width:min(430px,calc(100vw - 32px));max-height:min(680px,calc(100vh - 48px));overflow:auto;background:#fff;color:#202124;border:1px solid #dadce0;border-radius:16px;box-shadow:0 8px 28px rgba(60,64,67,.3);padding:20px;font:14px/1.45 Arial,sans-serif}#${UI.popup} h2{font-size:19px;margin:0 0 6px}#${UI.popup} p{margin:8px 0}#${UI.popup} .sentinel-score{font-size:28px;font-weight:700;margin:12px 0}#${UI.popup} .sentinel-high{color:#b3261e}#${UI.popup} .sentinel-suspicious{color:#9a6700}#${UI.popup} .sentinel-low{color:#137333}#${UI.popup} ul{padding-left:20px}#${UI.popup} li{margin:7px 0}#${UI.popup} small{color:#5f6368}#${UI.popup} .sentinel-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}#${UI.popup} button{min-height:34px;padding:0 12px;border:1px solid #dadce0;border-radius:8px;background:#fff;color:#1a73e8;font-weight:600;cursor:pointer}#${UI.popup} details{border-top:1px solid #eee;margin-top:16px;padding-top:12px}#${UI.popup} .sentinel-flow{padding:10px;background:#f6f8fc;border-radius:8px;font-size:12px}`;
  document.head.append(style);
}

function element<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag); if (text) node.textContent = text; if (className) node.className = className; return node;
}

function showPopup(title: string, message: string): HTMLElement {
  document.getElementById(UI.popup)?.remove(); const popup = element("section"); popup.id = UI.popup; popup.setAttribute("role", "dialog"); popup.setAttribute("aria-live", "polite");
  popup.append(element("h2", title), element("p", message)); document.body.append(popup); return popup;
}

function riskLabel(result: ExtensionResult): { label: string; css: string } {
  const category = riskCategoryFromScore(result.analysis.emailRiskScore);
  return { label: riskCategoryLabel(category), css: `sentinel-${category}` };
}

function renderResult(result: ExtensionResult): void {
  const popup = showPopup("Email Security Analysis", "Analysis complete."); const risk = riskLabel(result);
  popup.append(element("div", `${risk.label} · ${result.analysis.emailRiskScore}/100`, `sentinel-score ${risk.css}`));
  popup.append(element("small", `Source: ${result.analysis.scoreSource}. This assessment indicates risk; it does not guarantee safety.`));
  const behaviors = result.analysis.detectedBehaviors.slice(0, 4);
  if (behaviors.length) { popup.append(element("h3", "Strongest indicators")); const list = element("ul"); behaviors.forEach((item) => { const li = element("li"); li.append(element("strong", normalizeBehaviorLabel(item.type) ?? item.type.replaceAll("_", " ")), element("div", item.evidence)); list.append(li); }); popup.append(list); }
  const technical = result.analysis.detectedBehaviors.filter((item) => ["sender_domain_mismatch", "suspicious_url"].includes(item.type));
  if (technical.length) { popup.append(element("h3", "Technical indicators")); technical.forEach((item) => popup.append(element("p", item.evidence))); }
  popup.append(element("h3", "Recommended action"), element("p", result.analysis.recommendation));
  const details = element("details"), summary = element("summary", "How was this analyzed?"); details.append(summary, element("p", "The system examines the email’s language, sender information, links, and social-engineering behaviors. These indicators are converted into measurable features and processed to generate the final risk assessment."), element("div", "Email Content → Behavioral and Technical Analysis → Classification → Risk Score and Explanation", "sentinel-flow")); popup.append(details);
  const actions = element("div", undefined, "sentinel-actions"); const view = element("button", "View Full Analysis"), report = element("button", "Report as Suspicious"), close = element("button", "Close");
  view.onclick = async () => { view.disabled = true; await chrome.runtime.sendMessage({ type: "RECORD_SCAN_FEEDBACK", feedback: { scanId: result.analysis.scanId, messageId: result.analysis.messageId, action: "view_full_analysis", createdAt: new Date().toISOString() } } satisfies RuntimeMessage); await chrome.runtime.sendMessage({ type: "OPEN_SCAN_DASHBOARD", scanId: result.analysis.scanId } satisfies RuntimeMessage); };
  report.onclick = async () => { report.disabled = true; const response = await chrome.runtime.sendMessage({ type: "RECORD_SCAN_FEEDBACK", feedback: { scanId: result.analysis.scanId, messageId: result.analysis.messageId, action: "reported_suspicious", createdAt: new Date().toISOString() } } satisfies RuntimeMessage); report.textContent = response?.ok ? "Reported" : "Report failed — retry"; report.disabled = Boolean(response?.ok); };
  close.onclick = () => popup.remove(); actions.append(view, report, close); popup.append(actions);
}

async function scan(button: HTMLButtonElement): Promise<void> {
  if (scanning) return; scanning = true; button.disabled = true; button.lastChild!.textContent = "Scanning…";
  showPopup("Email Security Analysis", "Scanning this email for phishing and social-engineering indicators…");
  try {
    const email = await extractForScan();
    if (!email.bodyText?.trim()) throw new EmailSourceUnavailableError("This message has no readable text content to analyze.");
    const response = await Promise.race([chrome.runtime.sendMessage({ type: "PROCESS_EMAIL", email } satisfies RuntimeMessage), new Promise<never>((_, reject) => window.setTimeout(() => reject(new Error("The scan timed out. Please try again.")), 20_000))]);
    if (!response?.ok) throw new Error(response?.error ?? "Analysis unavailable."); renderResult(response.result as ExtensionResult);
  } catch (error) { const popup = showPopup("Email Security Analysis", error instanceof Error ? error.message : "The scan could not be completed."); popup.setAttribute("role", "alert"); }
  finally { scanning = false; button.disabled = false; button.lastChild!.textContent = "Scan"; }
}

async function injectScanButton(): Promise<void> {
  let email; try { email = await extractForScan(); } catch { document.getElementById(UI.button)?.remove(); return; }
  if (activeMessageId !== email.messageId) { activeMessageId = email.messageId; document.getElementById(UI.popup)?.remove(); scanning = false; }
  const actionArea = GMAIL_SELECTORS.messageActions.map((selector) => document.querySelector<HTMLElement>(selector)).find(Boolean); if (!actionArea) return;
  const forward = GMAIL_SELECTORS.forwardButtons.map((selector) => actionArea.querySelector<HTMLElement>(selector)).find(Boolean);
  const insertionArea = forward?.parentElement ?? actionArea;
  ensureScanButton(insertionArea, forward ?? null, (button) => void scan(button));
}

chrome.runtime.onMessage.addListener((message: RuntimeMessage, _sender, sendResponse) => {
  if (message.type === "PING_CONTENT_SCRIPT") {
    sendResponse({ ok: true, source: "sentinel-content-script" });
    return false;
  }
  if (message.type !== "GET_CURRENT_EMAIL") return false;
  void extractCurrent().then((email) => sendResponse({ ok: true, email })).catch((error) => sendResponse({
    ok: false, error: error instanceof EmailSourceUnavailableError ? error.message : "Gmail metadata is unavailable."
  }));
  return true;
});

async function considerAutomaticTracking(): Promise<void> {
  const settings = await loadSettings();
  if (!settings.automaticTracking || settings.sourceMode !== "gmail") return;
  try {
    const email = await extractCurrent();
    if (!trackingGuard.shouldTrack(email.messageId)) return;
    await chrome.runtime.sendMessage({ type: "PROCESS_EMAIL", email } satisfies RuntimeMessage);
  } catch {
    // A closed conversation or Gmail layout change is an unavailable state, not a page error.
  }
}

const observeTarget = document.querySelector("main, [role='main']") ?? document.body;
const observer = new MutationObserver(() => {
  window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(() => { void considerAutomaticTracking(); void injectScanButton(); }, 600);
});
observer.observe(observeTarget, { childList: true, subtree: true });
window.addEventListener("pagehide", () => { observer.disconnect(); window.clearTimeout(debounceTimer); }, { once: true });
void considerAutomaticTracking();
addStyles(); void injectScanButton();
