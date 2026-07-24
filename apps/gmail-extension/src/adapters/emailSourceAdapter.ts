import type { EmailSourceMetadata } from "@phishing-defense/shared";

export class EmailSourceUnavailableError extends Error {}

export interface EmailSourceAdapter {
  extractCurrentEmail(): Promise<EmailSourceMetadata>;
}
