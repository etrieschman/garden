from typing import Protocol

from garden.domain import Taxon


class CatalogProvider(Protocol):
    """Resolves human-typed names ('Garden Gem tomato') into Taxon records.

    A future USDA PLANTS scraper will implement this same Protocol.
    """

    name: str

    def lookup(self, query: str) -> Taxon | None:
        """Best-effort exact-ish match. Returns None if not found."""
