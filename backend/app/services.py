from .repository import TrackedEmailRepository
from .schemas import EmailOpenRequest, RiskLevel, TrackedEmailResponse


class EmailInteractionService:
    def __init__(self, repository: TrackedEmailRepository, deduplication_seconds: int) -> None:
        self.repository = repository
        self.deduplication_seconds = deduplication_seconds

    @staticmethod
    def temporary_rule_score(request: EmailOpenRequest) -> tuple[int, RiskLevel]:
        """Transparent demo-only scoring; visit count is intentionally not an input."""
        subject = request.subject.lower()
        score = 0
        if any(term in subject for term in ("immediately", "urgent", "act now")):
            score += 35
        if any(term in subject for term in ("verify", "confirm", "account")):
            score += 25
        if request.sender_name.lower().startswith("unknown"):
            score += 15
        score = min(score, 100)
        level = RiskLevel.HIGH if score >= 70 else RiskLevel.MEDIUM if score >= 40 else RiskLevel.LOW
        return score, level

    def record_open(self, request: EmailOpenRequest) -> TrackedEmailResponse:
        score, level = self.temporary_rule_score(request)
        return self.repository.record_email_open(request, score, level, self.deduplication_seconds)
