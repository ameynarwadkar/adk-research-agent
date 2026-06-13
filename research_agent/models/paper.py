"""
Paper-related models — the core academic data structures.

These models represent papers fetched from ArXiv, PubMed, OpenAlex,
and Semantic Scholar. They are the shared data contract between all
agents and tools in the pipeline.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Author(BaseModel):
    """An academic paper author."""

    name: str
    author_id: str | None = Field(
        default=None,
        description="External author ID (Semantic Scholar, ORCID, etc.)",
    )

    def __str__(self) -> str:
        return self.name


class Paper(BaseModel):
    """An academic paper with metadata.

    This is the central data structure — everything flows through Papers.
    Fields are intentionally nullable because APIs don't always return
    complete data.
    """

    paper_id: str = Field(description="Paper identifier (ArXiv ID, PMID, OpenAlex ID, etc.)")
    title: str
    authors: list[Author] = Field(default_factory=list)
    abstract: str | None = Field(
        default=None,
        description="Paper abstract. Can be None if not fetched or unavailable.",
    )
    year: int | None = Field(default=None, description="Publication year.")
    fields_of_study: list[str] = Field(
        default_factory=list,
        description="Fields/categories of the paper.",
    )
    citation_count: int = Field(default=0, description="Total citation count.")
    venue: str | None = Field(default=None, description="Publication venue.")
    url: str = Field(default="", description="URL of the paper.")
    tldr: str | None = Field(
        default=None,
        description="Auto-generated TLDR summary.",
    )
    is_open_access: bool = Field(default=False)

    @property
    def authors_str(self) -> str:
        """Format authors as 'Author1, Author2, and Author3'."""
        names = [a.name for a in self.authors]
        if not names:
            return "Unknown"
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return f"{', '.join(names[:-1])}, and {names[-1]}"

    @property
    def citation_str(self) -> str:
        """APA-style short citation: 'Author et al. (2025)'."""
        if not self.authors:
            first_author = "Unknown"
        else:
            first_author = self.authors[0].name.split()[-1]  # last name
        et_al = " et al." if len(self.authors) > 2 else ""
        year = self.year or "n.d."
        return f"{first_author}{et_al} ({year})"

    def __str__(self) -> str:
        return f"{self.citation_str}: {self.title}"


class PaperCollection(BaseModel):
    """A batch of papers returned from a search or filter operation."""

    papers: list[Paper] = Field(default_factory=list)
    query: str = Field(description="The search query that produced these papers.")
    total_results: int = Field(
        default=0,
        description="Total results available (may exceed papers returned).",
    )
    filters_applied: list[str] = Field(
        default_factory=list,
        description="Human-readable list of filters applied to the results.",
    )

    @property
    def count(self) -> int:
        """Number of papers in this collection."""
        return len(self.papers)