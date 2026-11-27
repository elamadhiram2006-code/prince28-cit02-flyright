"""Strict structured metadata schema for extracted FlyRight documents."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocMeta(BaseModel):
    """Document-level metadata extracted from source text."""

    model_config = ConfigDict(extra="forbid")

    doc_kind: Literal[
        "guideline",
        "rule",
        "notice",
        "list",
        "report",
        "faq",
        "form",
        "tutorial",
        "reference",
        "other",
    ]

    year: int | None = Field(default=None, ge=1950, le=2027)

    language: Literal["en", "ta", "hi", "other"]

    summary: str = Field(min_length=20, max_length=300)

    topics: list[str] = Field(min_length=1, max_length=6)

    rule: list[str] = Field(default_factory=list, max_length=8)
    situation: list[str] = Field(default_factory=list, max_length=8)
    flight_duration: list[str] = Field(default_factory=list, max_length=8)
    compensation: list[str] = Field(default_factory=list, max_length=8)
    facilities: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("topics")
    @classmethod
    def normalize_topics(cls, values: list[str]) -> list[str]:
        """Lowercase, trim, and deduplicate topics."""
        result = []
        seen = set()

        for value in values:
            topic = value.strip().lower()
            if topic and topic not in seen:
                seen.add(topic)
                result.append(topic)

        if not result:
            raise ValueError("topics must contain at least one non-empty value")

        if len(result) > 6:
            raise ValueError("topics must contain no more than 6 unique values")

        return result

    @field_validator(
        "rule",
        "situation",
        "flight_duration",
        "compensation",
        "facilities",
    )
    @classmethod
    def clean_list_values(cls, values: list[str]) -> list[str]:
        """Trim list values and reject empty or excessively long entries."""
        result = []

        for value in values:
            item = value.strip()
            if not item:
                raise ValueError("list values must not be empty")
            if len(item) > 120:
                raise ValueError("list values must not exceed 120 characters")
            result.append(item)

        return result
