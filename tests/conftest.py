"""Shared pytest fixtures for the research_agent test suite."""

import pytest

from research_agent.models.paper import Author, Paper


@pytest.fixture
def author_alice() -> Author:
    return Author(name="Alice Brown")


@pytest.fixture
def author_bob() -> Author:
    return Author(name="Bob Chen")


@pytest.fixture
def author_carol() -> Author:
    return Author(name="Carol Davis")


@pytest.fixture
def sample_paper(author_alice, author_bob, author_carol) -> Paper:
    return Paper(
        paper_id="arxiv:2401.00001",
        title="Intermittent Fasting and Metabolic Health: A Review",
        authors=[author_alice, author_bob, author_carol],
        abstract=(
            "This paper reviews the effects of intermittent fasting on "
            "metabolic health markers including blood glucose and insulin sensitivity."
        ),
        year=2024,
        citation_count=42,
        venue="Journal of Nutrition",
        is_open_access=True,
        fields_of_study=["Medicine", "Nutrition"],
    )


@pytest.fixture
def minimal_paper() -> Paper:
    """A paper with only required fields set."""
    return Paper(paper_id="test:001", title="Minimal Paper")


@pytest.fixture
def paper_list(sample_paper) -> list[Paper]:
    """A small list of varied papers for filter/rank tests."""
    p2 = Paper(
        paper_id="arxiv:2301.00002",
        title="Continuous Caloric Restriction in Diabetes",
        authors=[Author(name="Zara Ahmed")],
        abstract="Study on continuous caloric restriction in type 2 diabetes patients.",
        year=2022,
        citation_count=105,
        venue="Diabetes Care",
        is_open_access=False,
        fields_of_study=["Medicine"],
    )
    p3 = Paper(
        paper_id="pubmed:99999",
        title="Alpha-Level Neural Networks",
        authors=[],
        abstract=None,
        year=2018,
        citation_count=0,
        venue=None,
        is_open_access=True,
        fields_of_study=[],
    )
    return [sample_paper, p2, p3]


@pytest.fixture
def paper_dicts(paper_list) -> list[dict]:
    """paper_list serialised to dicts (as tools receive them)."""
    return [p.model_dump() for p in paper_list]
