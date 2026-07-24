/** All Gmail DOM assumptions live here so breakage is isolated and reviewable. */
export const GMAIL_SELECTORS = {
  messageContainers: ["[data-legacy-message-id]", "[data-message-id]", "div.adn"],
  sender: ["[email]", "[data-hovercard-id]", "span.go"],
  subject: ["h2.hP", "[data-thread-perm-id] h2", "h2"],
  messageIdAttributes: ["data-legacy-message-id", "data-message-id"]
  ,messageBody: [".a3s"]
  ,messageActions: ["[role='main'] .amn", ".amn", ".gA.gt.acV", ".gA.gt"]
  ,replyButtons: ["[role='button'][aria-label^='Reply']", ".amn > .ams"]
  ,forwardButtons: ["[role='button'][aria-label^='Forward']", ".amn > .ams:last-child"]
} as const;
