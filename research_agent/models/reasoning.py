from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field

class EvidenceScore(BaseModel):
    paper_id: str = Field(description="ID of the paper being graded.")
    relevance: float = Field(ge=0.0, le=1.0, description="Semantic relevance of the paper to the query (0-1).")
    recency: float = Field(ge=0.0, le=1.0, description="Recency score: 1.0 for current-year papers, decaying for older ones.")
    source_quality: float = Field(ge=0.0, le=1.0, description="Heuristic quality based on venue/journal tier (0-1).")

    @property
    def overall(self) -> float:
        return 0.5 * self.relevance + 0.25 * self.recency + 0.25 * self.source_quality

    @property
    def tier(self) -> Literal["strong", "moderate", "weak"]:
        score = self.overall
        if score >= 0.7: return "strong"
        if score >= 0.4: return "moderate"
        return "weak"

class ClaimVerification(BaseModel):
    claim_text: str = Field(description="The claim being verified.")
    is_verified: bool = Field(description="True if the claim is grounded in at least one source paper.")
    best_matching_paper_id: Optional[str] = Field(default=None, description="Paper ID with the highest similarity to the claim.")
    similarity_score: float = Field(default=0.0, description="Cosine similarity between the claim and the best-matching abstract.")
    confidence: Literal["strong", "moderate", "weak", "unverified"] = Field(description="Confidence level derived from verification result.")

class GapAnalysis(BaseModel):
    theme: str = Field(description="The theme being evaluated.")
    paper_count: int = Field(description="Number of papers covering this theme.")
    is_adequate: bool = Field(description="True if the theme has sufficient coverage (>= 2 papers).")
    gap_description: Optional[str] = Field(default=None, description="Human-readable description of the gap, if any.")

class ReQueryRequest(BaseModel):
    queries: list[str] = Field(description="New search queries to fill identified gaps.")
    reason: str = Field(description="Explanation of why re-querying is needed.")

class ReasonerOutput(BaseModel):
    evidence_scores: list[EvidenceScore] = Field(default_factory=list, description="Quality scores for each paper evaluated.")
    claim_verifications: list[ClaimVerification] = Field(default_factory=list, description="Verification results for each claim checked.")
    gap_analyses: list[GapAnalysis] = Field(default_factory=list, description="Coverage analysis for each theme.")
    self_critique: str = Field(default="", description="LLM self-critique of the evidence grading and verification results.")
    re_query_request: Optional[ReQueryRequest] = Field(default=None, description="If gaps were found, a request to re-run search with new queries.")

    @property
    def has_gaps(self) -> bool:
        return any(not ga.is_adequate for ga in self.gap_analyses)

    @property
    def underserved_themes(self) -> list[str]:
        return [ga.theme for ga in self.gap_analyses if not ga.is_adequate]
