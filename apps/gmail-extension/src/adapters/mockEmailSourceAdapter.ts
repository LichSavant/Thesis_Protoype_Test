import type { EmailSourceMetadata } from "@phishing-defense/shared";
import type { EmailSourceAdapter } from "./emailSourceAdapter";

export class MockEmailSourceAdapter implements EmailSourceAdapter {
  async extractCurrentEmail(): Promise<EmailSourceMetadata> {
    return {
      userId: "demo-user-001", messageId: "demo-message-001",
      senderEmail: "unknown@example.com", senderName: "Unknown Sender", senderDomain: "example.com",
      subject: "Verify your account immediately", openedAt: new Date().toISOString(), links: []
    };
  }
}
