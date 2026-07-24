import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EmailScanRecord } from "@phishing-defense/shared";
import { normalizeBehaviorLabel } from "@phishing-defense/shared";
import { App, scanRisk } from "./App";
import { getEmailScan, getEmailScans } from "./api";

vi.mock("./api", () => ({ getEmailScans: vi.fn(), getEmailScan: vi.fn() }));
const mockedGet = vi.mocked(getEmailScans);
const mockedGetOne = vi.mocked(getEmailScan);

function scan(score: number, id: string, behaviors = ["urgency"]): EmailScanRecord {
  return { scanId: id, scannedAt: `2026-01-0${id}T10:00:00Z`, messageId: `message-${id}`, subject: `Subject ${id}`,
    senderName: `Sender ${id}`, senderEmail: `sender${id}@example.com`, senderDomain: "example.com", classification: score >= 65 ? "phishing" : score >= 30 ? "uncertain" : "legitimate",
    emailRiskScore: score, riskLevel: score >= 65 ? "high" : score >= 30 ? "moderate" : "low", scoreSource: "rule-based", modelVersion: null,
    detectedBehaviors: behaviors.map(type => ({ type, confidence: .8, evidence: `${type} phrase` })), recommendation: "Verify the sender.",
    urlCount: 1, suspiciousUrls: [], technicalIndicators: [], phishingProbability: null,
    userReported: false, emailOpened: true, viewFullAnalysisSelected: false };
}

describe("dashboard", () => {
  beforeEach(() => { mockedGet.mockReset(); mockedGetOne.mockReset(); window.history.replaceState({}, "", "/"); });
  it("renders loading and empty states", async () => { let finish!: (value: []) => void; mockedGet.mockReturnValue(new Promise(resolve => { finish = resolve; })); render(<App/>); expect(screen.getByRole("status")).toHaveTextContent("Loading security analyses"); finish([]); expect(await screen.findByText("No email scans yet")).toBeInTheDocument(); });
  it("calculates low, suspicious, and high summaries from scans", async () => { mockedGet.mockResolvedValue([scan(12,"1"),scan(45,"2",["authority","credential_request"]),scan(82,"3",["fear_or_threat"])]); render(<App/>); expect(await screen.findByText("Subject 3")).toBeInTheDocument(); expect(screen.getByText("High-Risk Emails").parentElement).toHaveTextContent("1"); expect(screen.getByText("Suspicious Emails").parentElement).toHaveTextContent("1"); expect(screen.getByText("Low-Risk Emails").parentElement).toHaveTextContent("1"); expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument(); });
  it("searches scans and opens details with multiple behaviors", async () => { mockedGet.mockResolvedValue([scan(45,"2",["urgency","authority","credential_request"]),scan(12,"1")]); render(<App/>); await screen.findByText("Subject 2"); fireEvent.change(screen.getByPlaceholderText("Search subject or sender"), { target: { value: "Sender 2" } }); expect(screen.queryByText("Subject 1")).not.toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "View details" })); expect(screen.getByRole("dialog")).toHaveTextContent("Credential Request"); });
  it("shows an API error", async () => { mockedGet.mockRejectedValue(new Error("offline")); render(<App/>); expect(await screen.findByRole("alert")).toHaveTextContent("Couldn’t load scan records"); });
  it("shows a useful error for an invalid direct scan link", async () => { mockedGet.mockResolvedValue([]); mockedGetOne.mockRejectedValue(new Error("The requested scan could not be found.")); window.history.replaceState({}, "", "/?scanId=missing"); render(<App/>); expect(await screen.findByRole("alert")).toHaveTextContent("requested scan could not be found"); });
  it("loads full analysis directly by stable scan identifier", async () => { const record = scan(45, "2", ["urgency"]); mockedGet.mockResolvedValue([]); mockedGetOne.mockResolvedValue(record); window.history.replaceState({}, "", "/?scanId=2"); render(<App/>); expect(await screen.findByRole("dialog")).toHaveTextContent("Subject 2"); expect(mockedGetOne).toHaveBeenCalledWith("2"); });
});

describe("analysis normalization", () => {
  it("normalizes backend behavior aliases", () => { expect(normalizeBehaviorLabel("fear-or-threat")).toBe("Fear"); expect(normalizeBehaviorLabel("credential request")).toBe("Credential Request"); expect(normalizeBehaviorLabel("suspicious_url")).toBeNull(); });
  it("maps scores consistently", () => { expect(scanRisk(scan(10,"1"))).toBe("low"); expect(scanRisk(scan(30,"2"))).toBe("suspicious"); expect(scanRisk(scan(65,"3"))).toBe("high"); });
});
