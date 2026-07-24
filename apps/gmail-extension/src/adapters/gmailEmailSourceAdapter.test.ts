import { describe, expect, it } from "vitest";
import fixture from "../fixtures/gmail-open-message.html?raw";
import { GmailEmailSourceAdapter } from "./gmailEmailSourceAdapter";
import { extractDomain, identityFromHash, parseSender } from "./gmailParsing";

describe("Gmail parsing", () => {
  it("parses display name and sender email", () => expect(parseSender("Jane Doe <jane@example.com>")).toEqual({ name: "Jane Doe", email: "jane@example.com" }));
  it("extracts sender domain", () => expect(extractDomain("Jane@Example.COM")).toBe("example.com"));
  it("extracts a route message identity", () => expect(identityFromHash("#inbox/FMfcgzQZSabcdefghijkl")).toBe("gmail-route:FMfcgzQZSabcdefghijkl"));
});

describe("GmailEmailSourceAdapter fixture", () => {
  it("extracts only the opened fixture message metadata", async () => {
    document.body.innerHTML = fixture;
    const result = await new GmailEmailSourceAdapter(document, { includeLinks: true }).extractCurrentEmail();
    expect(result.messageId).toBe("fixture-message-123");
    expect(result.senderEmail).toBe("security@unrelated-example.com");
    expect(result.senderDomain).toBe("unrelated-example.com");
    expect(result.subject).toContain("Microsoft");
    expect(result.links).toHaveLength(1);
    expect(result.bodyText).toBeUndefined();
  });
  it("fails gracefully when no message is selected", async () => {
    document.body.innerHTML = "<main role='main'></main>";
    await expect(new GmailEmailSourceAdapter(document).extractCurrentEmail()).rejects.toThrow("Open a Gmail message");
  });
  it("normalizes formatted message text only when explicitly authorized", async () => {
    document.body.innerHTML = `<h2 class="hP">Formatted</h2><div data-legacy-message-id="html-1"><span email="sender@example.com" name="Sender"></span><div class="a3s"><b>Urgent</b><br>verify account</div></div>`;
    const body = document.querySelector<HTMLElement>(".a3s")!; Object.defineProperty(body, "innerText", { value: "Urgent   verify account\n\n\nnow" });
    const result = await new GmailEmailSourceAdapter(document, { includeBody: true, bodyAuthorized: true }).extractCurrentEmail();
    expect(result.bodyText).toBe("Urgent verify account\n\nnow");
  });
  it("deduplicates multiple links from the selected message", async () => {
    document.body.innerHTML = `<h2 class="hP">Links</h2><div data-legacy-message-id="links-1"><span email="sender@example.com" name="Sender"></span><div class="a3s"><a href="https://one.example/a">one</a><a href="https://two.example/b">two</a><a href="https://one.example/a">again</a></div></div>`;
    const result = await new GmailEmailSourceAdapter(document, { includeLinks: true }).extractCurrentEmail();
    expect(result.links).toHaveLength(2);
  });
  it("uses the latest visible message in a conversation thread", async () => {
    document.body.innerHTML = `<h2 class="hP">Thread</h2><div data-legacy-message-id="older"><span email="old@example.com" name="Old"></span><div class="a3s">old</div></div><div data-legacy-message-id="latest"><span email="new@example.com" name="New"></span><div class="a3s">new</div></div>`;
    const result = await new GmailEmailSourceAdapter(document).extractCurrentEmail();
    expect(result.messageId).toBe("latest"); expect(result.senderEmail).toBe("new@example.com");
  });
});
