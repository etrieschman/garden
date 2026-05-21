from typing import Any

from pydantic import BaseModel, Field


class Taxon(BaseModel):
    """A species + optional cultivar. Reference data — many plants share one taxon."""

    id: str
    scientific_name: str
    common_name: str | None = None
    cultivar: str | None = None
    category: str | None = None  # "vegetable" | "herb" | "fruit" | "flower" | ...
    source: str | None = None    # provenance: "usda-plants" | "manual" | ...
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def display_name(self) -> str:
        if self.cultivar and self.common_name:
            return f"{self.common_name} '{self.cultivar}'"
        if self.cultivar:
            return f"{self.scientific_name} '{self.cultivar}'"
        return self.common_name or self.scientific_name
