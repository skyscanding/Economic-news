"""Normalized data model shared across the pipeline."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Headline:
    title: str
    url: str
    vendor: str
    section: str                       # one of feeds.SECTIONS
    published: datetime | None         # timezone-aware UTC, or None if absent
    summary: str = ""

    # Populated later in the pipeline:
    alternates: list[dict] = field(default_factory=list)   # dupes: {vendor,url}
    score: float | None = None         # 0-10 relevance/materiality from the ranker
    reason: str = ""                   # one-line justification from the ranker
    keyword_hits: list[str] = field(default_factory=list)  # cheap cross-check
    affects: list[dict] = field(default_factory=list)      # portfolio: {ticker,channel}

    @property
    def age_hours(self) -> float | None:
        if not self.published:
            return None
        delta = datetime.now(timezone.utc) - self.published
        return delta.total_seconds() / 3600.0

    def sort_key(self) -> tuple:
        # Higher score first; then newer first. None-safe.
        s = self.score if self.score is not None else -1.0
        ts = self.published.timestamp() if self.published else 0.0
        return (-s, -ts)

    def to_dict(self) -> dict:
        """JSON-serializable form for the web front end's API."""
        return {
            "title": self.title,
            "url": self.url,
            "vendor": self.vendor,
            "section": self.section,
            "published": self.published.isoformat() if self.published else None,
            "age_hours": self.age_hours,
            "score": self.score,
            "reason": self.reason,
            "keyword_hits": self.keyword_hits,
            "affects": self.affects,
            "alternates": self.alternates,
        }
