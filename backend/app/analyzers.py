from abc import ABC, abstractmethod
from urllib.parse import urlparse
from datetime import datetime, timezone
from uuid import uuid4

from .schemas import (
    AnalysisRiskLevel, AnalyzeEmailRequest, AnalyzeEmailResponse, Classification, DetectedBehavior,
)


class Analyzer(ABC):
    """Stable analysis boundary for future BRL, feature extractors, and ML models."""

    @abstractmethod
    def analyze(self, request: AnalyzeEmailRequest) -> AnalyzeEmailResponse: ...


class RuleBasedAnalyzer(Analyzer):
    def analyze(self, request: AnalyzeEmailRequest) -> AnalyzeEmailResponse:
        text = f"{request.subject} {request.body_text or ''}".lower()
        behaviors: list[DetectedBehavior] = []
        score = 0

        score += self._text_indicator(behaviors, text, "urgency", ("immediately", "urgent", "act now"), 35, .91)
        score += self._text_indicator(behaviors, text, "fear_or_threat", ("suspended", "locked", "terminated", "penalty"), 15, .86)
        score += self._text_indicator(behaviors, text, "credential_request", ("password", "login", "verify", "sign in"), 25, .90)
        score += self._text_indicator(behaviors, text, "authority", ("administrator", "security team", "government", "bank"), 8, .70)
        score += self._text_indicator(behaviors, text, "impersonation", ("support team", "official notice", "account team"), 10, .75)
        score += self._text_indicator(behaviors, text, "reward", ("prize", "reward", "winner", "gift"), 10, .82)
        score += self._text_indicator(behaviors, text, "scarcity", ("limited time", "expires today", "only today"), 8, .80)
        if request.sender_name.lower().startswith("unknown") and not any(item.type == "impersonation" for item in behaviors):
            behaviors.append(DetectedBehavior(type="impersonation", confidence=.55, evidence="Sender identity is unknown"))
            score += 15

        sender_domain = request.sender_domain.lower()
        if self._domain_mismatch(text, sender_domain):
            behaviors.append(DetectedBehavior(type="sender_domain_mismatch", confidence=.84, evidence=f"Claimed organization differs from {sender_domain}"))
            score += 18
        suspicious_link = self._suspicious_link(request.links, sender_domain)
        if suspicious_link:
            behaviors.append(DetectedBehavior(type="suspicious_url", confidence=.88, evidence=suspicious_link))
            score += 20

        score = min(score, 100)
        level = self.risk_level(score)
        classification = Classification.PHISHING if score >= 70 else Classification.LEGITIMATE if score < 20 else Classification.UNCERTAIN
        recommendation = (
            "Do not click links or provide credentials; verify the sender through a trusted channel."
            if score >= 70 else "Verify the sender before clicking links." if score >= 20
            else "No strong prototype indicators were detected; remain cautious with unexpected requests."
        )
        return AnalyzeEmailResponse(
            scan_id=str(uuid4()), scanned_at=datetime.now(timezone.utc),
            message_id=request.message_id, classification=classification, email_risk_score=score,
            risk_level=level, score_source="rule-based", detected_behaviors=behaviors,
            recommendation=recommendation, model_version=None,
        )

    @staticmethod
    def risk_level(score: int) -> AnalysisRiskLevel:
        if score >= 85: return AnalysisRiskLevel.CRITICAL
        if score >= 65: return AnalysisRiskLevel.HIGH
        if score >= 30: return AnalysisRiskLevel.MODERATE
        return AnalysisRiskLevel.LOW

    @staticmethod
    def _text_indicator(behaviors, text, name, terms, points, confidence) -> int:
        match = next((term for term in terms if term in text), None)
        if not match: return 0
        behaviors.append(DetectedBehavior(type=name, confidence=confidence, evidence=match))
        return points

    @staticmethod
    def _domain_mismatch(text: str, sender_domain: str) -> bool:
        known = {"google": "google.com", "microsoft": "microsoft.com", "paypal": "paypal.com"}
        return any(brand in text and not sender_domain.endswith(domain) for brand, domain in known.items())

    @staticmethod
    def _suspicious_link(links: list[str], sender_domain: str) -> str | None:
        for link in links:
            try:
                parsed = urlparse(link)
                host = (parsed.hostname or "").lower()
                if parsed.scheme != "https" or "@" in link or host.replace(".", "").isdigit() or (host and not host.endswith(sender_domain)):
                    return link[:300]
            except ValueError:
                return link[:300]
        return None
