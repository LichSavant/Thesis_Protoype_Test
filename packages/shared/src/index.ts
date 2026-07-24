export type RiskLevel = "low" | "medium" | "high";
export type ScoreSource = "mock-rule-based";
export type AnalysisRiskLevel = "low" | "moderate" | "high" | "critical";
export type Classification = "phishing" | "legitimate" | "uncertain";
export type RiskCategory = "low" | "suspicious" | "high";

/** Presentation mapping; raw analyzer classifications and levels remain stored unchanged. */
export function riskCategoryFromScore(score: number): RiskCategory {
  if (!Number.isFinite(score) || score < 0 || score > 100) throw new RangeError("Risk score must be between 0 and 100");
  return score >= 65 ? "high" : score >= 30 ? "suspicious" : "low";
}

export function riskCategoryLabel(category: RiskCategory): "Low Risk" | "Suspicious" | "High Risk" {
  return category === "high" ? "High Risk" : category === "suspicious" ? "Suspicious" : "Low Risk";
}

const behaviorLabels: Record<string, string> = {
  urgency: "Urgency", authority: "Authority", fear: "Fear", fear_or_threat: "Fear",
  curiosity: "Curiosity", scarcity: "Scarcity", reward: "Reward", credential_request: "Credential Request",
  impersonation: "Impersonation", trust_brand_exploitation: "Trust or Brand Exploitation", social_proof: "Social Proof"
};

export function normalizeBehaviorLabel(value: string): string | null {
  return behaviorLabels[value.toLowerCase().trim().replace(/[\s-]+/g, "_")] ?? null;
}

export interface EmailOpenRequest {
  userId: string;
  messageId: string;
  senderEmail: string;
  senderName: string;
  subject: string;
  openedAt: string;
}

export interface EmailSourceMetadata extends EmailOpenRequest {
  senderDomain: string;
  links?: string[];
  bodyText?: string;
}

export interface AnalyzeEmailRequest {
  schemaVersion: "1.0";
  messageId: string;
  senderEmail: string;
  senderName: string;
  senderDomain: string;
  subject: string;
  openedAt: string;
  links: string[];
  bodyText?: string;
  bodyCollectionAuthorized: boolean;
}

export interface DetectedBehavior {
  type: string;
  confidence: number;
  evidence: string;
}

export interface TechnicalIndicator {
  type: "sender_domain_mismatch" | "suspicious_url";
  evidence: string;
}

export interface EmailAnalysis {
  scanId: string;
  scannedAt: string;
  messageId: string;
  classification: Classification;
  emailRiskScore: number;
  riskLevel: AnalysisRiskLevel;
  scoreSource: "rule-based" | "ml-model";
  detectedBehaviors: DetectedBehavior[];
  recommendation: string;
  modelVersion: string | null;
}

export interface ScanFeedbackRequest { scanId: string; messageId: string; action: "reported_suspicious" | "view_full_analysis"; createdAt: string; }

export interface EmailScanRecord extends EmailAnalysis {
  subject: string;
  senderName: string;
  senderEmail: string;
  senderDomain: string;
  urlCount: number;
  suspiciousUrls: string[];
  technicalIndicators: TechnicalIndicator[];
  phishingProbability: number | null;
  userReported: boolean;
  emailOpened: boolean;
  viewFullAnalysisSelected: boolean;
}

export interface TrackedEmail {
  messageId: string;
  senderEmail: string;
  senderName: string;
  subject: string;
  visitCount: number;
  emailRiskScore: number;
  riskLevel: RiskLevel;
  scoreSource: ScoreSource;
  firstOpenedAt: string;
  lastOpenedAt: string;
}
