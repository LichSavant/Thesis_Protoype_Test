export const SCAN_BUTTON_ID = "sentinel-scan-button";

export function ensureScanButton(actionArea: HTMLElement, forwardButton: HTMLElement | null, onClick: (button: HTMLButtonElement) => void): HTMLButtonElement {
  const existing = document.getElementById(SCAN_BUTTON_ID);
  if (existing instanceof HTMLButtonElement && actionArea.contains(existing)) return existing;
  existing?.remove();
  const button = document.createElement("button");
  button.id = SCAN_BUTTON_ID;
  button.type = "button";
  button.setAttribute("aria-label", "Scan email for phishing indicators");
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24"); icon.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(icon.namespaceURI, "path");
  path.setAttribute("d", "M12 2 4.5 5v6c0 5 3.2 9.3 7.5 11 4.3-1.7 7.5-6 7.5-11V5L12 2Zm0 3.2 4.5 1.8v4c0 3.5-1.9 6.7-4.5 8.1C9.4 17.7 7.5 14.5 7.5 11V7L12 5.2Z");
  icon.append(path); button.append(icon, document.createTextNode("Scan"));
  button.onclick = () => onClick(button);
  actionArea.insertBefore(button, forwardButton);
  return button;
}
