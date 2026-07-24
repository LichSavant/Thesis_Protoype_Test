export type EmailSourceMode = "mock" | "gmail";
export interface ExtensionSettings { backendUrl: string; sourceMode: EmailSourceMode; automaticTracking: boolean; includeLinks: boolean; }
const defaults: ExtensionSettings = { backendUrl: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000", sourceMode: "mock", automaticTracking: false, includeLinks: false };

export function normalizeBackendUrl(value: string): string {
  const normalized = value.trim().replace(/\/$/, "");
  if (["http://localhost:8000", "http://localhost:5173", "http://127.0.0.1:5173"].includes(normalized)) return "http://127.0.0.1:8000";
  return normalized;
}

export async function loadSettings(): Promise<ExtensionSettings> {
  if (typeof chrome === "undefined" || !chrome.storage) return defaults;
  const result = await chrome.storage.local.get(Object.keys(defaults));
  const settings = { ...defaults, ...result } as ExtensionSettings;
  settings.backendUrl = normalizeBackendUrl(settings.backendUrl);
  return settings;
}
export async function saveSettings(settings: ExtensionSettings): Promise<void> {
  if (typeof chrome !== "undefined" && chrome.storage) await chrome.storage.local.set(settings);
}
