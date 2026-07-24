import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import type { EmailSourceMetadata } from "@phishing-defense/shared";
import { MockEmailSourceAdapter } from "./adapters/mockEmailSourceAdapter";
import type { ExtensionResult, RuntimeMessage } from "./messages";
import { ApiError, processEmail } from "./services/api";
import { loadSettings, saveSettings, type ExtensionSettings } from "./services/settings";
import "./popup.css";

const defaultSettings: ExtensionSettings = { backendUrl: "http://127.0.0.1:8000", sourceMode: "mock", automaticTracking: false, includeLinks: false };

export function Popup() {
  const [settings, setSettings] = useState(defaultSettings);
  const [result, setResult] = useState<ExtensionResult | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "success" | "offline" | "error">("idle");
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    void loadSettings().then(setSettings);
    if (typeof chrome !== "undefined" && chrome.storage) void chrome.storage.local.get("lastResult").then((stored) => {
      if (stored.lastResult) { setResult(stored.lastResult as ExtensionResult); setState("success"); }
    });
  }, []);

  async function onAnalyze() {
    setState("loading"); setMessage(""); setNotice("");
    try {
      await saveSettings(settings);
      const email = settings.sourceMode === "mock" ? await new MockEmailSourceAdapter().extractCurrentEmail() : await currentGmailEmail();
      setResult(await submitEmail(email)); setState("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unexpected analysis error.");
      setState(error instanceof ApiError && error.offline ? "offline" : "error");
    }
  }

  async function updateSettings(next: ExtensionSettings) { setSettings(next); await saveSettings(next); }

  return <main>
    <header><div className="mark">S</div><div><span className="eyebrow">EMAIL RISK ANALYSIS</span><h1>Sentinel prototype</h1></div></header>
    <section className="controls">
      <label>Email source<select aria-label="Email source" value={settings.sourceMode} onChange={(event) => void updateSettings({ ...settings, sourceMode: event.target.value as "mock" | "gmail" })}><option value="mock">Mock demo</option><option value="gmail">Current Gmail message</option></select></label>
      <label>Backend URL<input aria-label="Backend URL" value={settings.backendUrl} onChange={(event) => setSettings({ ...settings, backendUrl: event.target.value })} /></label>
      <label className="toggle"><input type="checkbox" checked={settings.automaticTracking} disabled={settings.sourceMode !== "gmail"} onChange={(event) => void updateSettings({ ...settings, automaticTracking: event.target.checked })}/><span>Automatic tracking</span></label>
      <label className="toggle"><input type="checkbox" checked={settings.includeLinks} onChange={(event) => void updateSettings({ ...settings, includeLinks: event.target.checked })}/><span>Include links for URL rules</span></label>
      <p className="tracking">Tracking: <strong>{settings.sourceMode === "gmail" && settings.automaticTracking ? "Automatic for selected Gmail messages" : "Manual only"}</strong></p>
    </section>
    <button className="primary" onClick={() => void onAnalyze()} disabled={state === "loading"}>{state === "loading" ? "Analyzing…" : settings.sourceMode === "gmail" ? "Analyze Current Email" : "Analyze Test Email"}</button>
    {state === "idle" && <p className="hint">Gmail mode reads only the selected message. Email bodies are disabled and never collected by this build.</p>}
    {(state === "offline" || state === "error") && <div role="alert" className="alert"><strong>{state === "offline" ? "Backend offline" : "Analysis unavailable"}</strong><p>{message}</p></div>}
    {result && state === "success" && <ResultCard result={result} onReport={() => setNotice("Use Gmail’s More menu → Report phishing. Sentinel has not sent a report or message content.")} />}
    {notice && <p className="notice" role="status">{notice}</p>}
    <details><summary>Privacy notice</summary><p>Sentinel reads only the selected message’s identifier, sender, domain, subject, and timestamp. Links are optional. Bodies, attachments, credentials, tokens, contacts, and unrelated inbox messages are excluded.</p></details>
  </main>;
}

function ResultCard({ result, onReport }: { result: ExtensionResult; onReport: () => void }) {
  const { trackedEmail, analysis } = result;
  return <section className="result">
    <Row label="Sender" value={trackedEmail.senderEmail} /><Row label="Sender domain" value={trackedEmail.senderEmail.split("@")[1] ?? "Unknown"}/>
    <Row label="Times Opened" value={String(trackedEmail.visitCount)} testId="visit-count" />
    <div className="score"><span>Prototype Email Risk Score</span><strong className={`risk ${analysis.riskLevel}`}>{analysis.emailRiskScore}% — {title(analysis.riskLevel)} Risk</strong><small>Source: {analysis.scoreSource}</small></div>
    <div className="behaviors"><span>Detected behaviors</span>{analysis.detectedBehaviors.length ? <ul>{analysis.detectedBehaviors.map((item) => <li key={`${item.type}-${item.evidence}`}><strong>{item.type.replaceAll("_", " ")}</strong><small>{Math.round(item.confidence * 100)}% · {item.evidence}</small></li>)}</ul> : <p>No strong prototype indicators detected.</p>}</div>
    <p className="recommendation">{analysis.recommendation}</p>
    <p className="disclaimer">Rule-based prototype result—not a trained ML prediction. Times opened is separate from email risk.</p>
    <div className="actions"><button onClick={() => void openDashboard()}>View in Dashboard</button><button onClick={onReport}>Report Email</button></div>
  </section>;
}

async function currentGmailEmail(): Promise<EmailSourceMetadata> {
  if (typeof chrome === "undefined" || !chrome.tabs) throw new Error("Gmail analysis is available only in the installed extension.");
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url?.startsWith("https://mail.google.com/")) throw new Error("Open and select a Gmail message, then try again.");
  try {
    const ping = await chrome.tabs.sendMessage(tab.id, { type: "PING_CONTENT_SCRIPT" } satisfies RuntimeMessage);
    if (!ping?.ok || ping.source !== "sentinel-content-script") throw new Error("Unexpected ping response");
  } catch {
    throw new Error("Sentinel could not load on this Gmail tab. Reload Gmail and try again.");
  }
  const response = await chrome.tabs.sendMessage(tab.id, { type: "GET_CURRENT_EMAIL" } satisfies RuntimeMessage);
  if (!response?.ok) throw new Error(response?.error ?? "Gmail metadata is unavailable.");
  return response.email as EmailSourceMetadata;
}

async function submitEmail(email: EmailSourceMetadata): Promise<ExtensionResult> {
  if (typeof chrome !== "undefined" && chrome.runtime?.sendMessage) {
    const response = await chrome.runtime.sendMessage({ type: "PROCESS_EMAIL", email } satisfies RuntimeMessage);
    if (!response?.ok) throw new Error(response?.error ?? "Analysis unavailable.");
    return response.result as ExtensionResult;
  }
  return processEmail((await loadSettings()).backendUrl, email);
}
async function openDashboard() { if (typeof chrome !== "undefined" && chrome.tabs) await chrome.tabs.create({ url: "http://localhost:5173" }); }
function Row({ label, value, testId }: { label: string; value: string; testId?: string }) { return <div className="row"><span>{label}</span><strong data-testid={testId}>{value}</strong></div>; }
function title(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
if (document.getElementById("root")) ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Popup /></React.StrictMode>);
