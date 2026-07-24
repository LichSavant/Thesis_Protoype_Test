export function parseSender(raw: string, explicitEmail?: string | null): { name: string; email: string } {
  const angleMatch = raw.match(/^\s*(.*?)\s*<([^<>\s]+@[^<>\s]+)>\s*$/);
  const email = (explicitEmail || angleMatch?.[2] || raw.match(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/)?.[0] || "").toLowerCase();
  if (!email) throw new Error("Sender email is unavailable");
  const name = (angleMatch?.[1] || raw.replace(email, "").replace(/[<>]/g, "").trim() || email.split("@")[0]).trim();
  return { name, email };
}

export function extractDomain(email: string): string {
  const parts = email.toLowerCase().split("@");
  if (parts.length !== 2 || !parts[1]) throw new Error("Sender domain is unavailable");
  return parts[1];
}

export function identityFromHash(hash: string): string | null {
  const parts = hash.split("/").filter(Boolean);
  const candidate = parts.reverse().find((part) => /^[A-Za-z0-9_-]{12,}$/.test(part));
  return candidate ? `gmail-route:${candidate}` : null;
}
