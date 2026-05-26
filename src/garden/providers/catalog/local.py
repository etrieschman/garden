"""Hand-curated catalog of common vegetable/herb cultivars.

Acts as the default CatalogProvider. A USDA-backed provider will eventually
fall back to this for cultivars USDA doesn't track.
"""

from __future__ import annotations

import re

from garden.domain import Taxon


def _slug(*parts: str) -> str:
    s = "-".join(p.lower() for p in parts if p)
    return re.sub(r"[^a-z0-9-]+", "-", s).strip("-")


# Minimal seed catalog. Add freely.
_SEED: list[Taxon] = [
    Taxon(
        id="solanum-lycopersicum--garden-gem",
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        cultivar="Garden Gem",
        category="vegetable",
        source="manual",
    ),
    Taxon(
        id="solanum-lycopersicum--improved-garden-gem",
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        cultivar="Improved Garden Gem",
        category="vegetable",
        source="UF Klee Lab",
    ),
    Taxon(
        id="solanum-lycopersicum--improved-garden-ruby",
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        cultivar="Improved Garden Ruby",
        category="vegetable",
        source="UF Klee Lab",
    ),
    Taxon(
        id="solanum-lycopersicum--improved-bw-hybrid",
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        cultivar="Improved BW Hybrid",
        category="vegetable",
        source="UF Klee Lab",
    ),
    Taxon(
        id="solanum-lycopersicum--cherokee-purple",
        scientific_name="Solanum lycopersicum",
        common_name="Tomato",
        cultivar="Cherokee Purple",
        category="vegetable",
        source="manual",
    ),
    Taxon(
        id="capsicum-annuum",
        scientific_name="Capsicum annuum",
        common_name="Pepper",
        category="vegetable",
        source="manual",
    ),
    Taxon(
        id="ocimum-basilicum",
        scientific_name="Ocimum basilicum",
        common_name="Basil",
        category="herb",
        source="manual",
    ),
    Taxon(
        id="cucumis-sativus",
        scientific_name="Cucumis sativus",
        common_name="Cucumber",
        category="vegetable",
        source="manual",
    ),
    Taxon(
        id="lactuca-sativa",
        scientific_name="Lactuca sativa",
        common_name="Lettuce",
        category="vegetable",
        source="manual",
    ),
]


class LocalCatalog:
    """Fuzzy-match against a static seed list; coin a new Taxon if no hit."""

    name = "local"

    def __init__(self, extra: list[Taxon] | None = None) -> None:
        self._entries: list[Taxon] = list(_SEED) + list(extra or [])

    def lookup(self, query: str) -> Taxon | None:
        q = query.lower().strip()
        if not q:
            return None

        # exact id
        for t in self._entries:
            if t.id == q:
                return t

        # exact cultivar or common name
        for t in self._entries:
            if t.cultivar and t.cultivar.lower() == q:
                return t
            if t.common_name and t.common_name.lower() == q:
                return t

        # substring on cultivar / common name
        hits = [
            t
            for t in self._entries
            if (t.cultivar and t.cultivar.lower() in q)
            or (t.common_name and t.common_name.lower() in q)
            or (t.cultivar and q in t.cultivar.lower())
        ]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            # Prefer the hit whose cultivar appears in the query
            cultivar_hits = [t for t in hits if t.cultivar and t.cultivar.lower() in q]
            if len(cultivar_hits) == 1:
                return cultivar_hits[0]

        return None

    def coin(self, query: str, category: str | None = None) -> Taxon:
        """Construct a placeholder Taxon when no entry matches.

        The user can refine the taxon's fields later. ID is derived from the query.
        """
        return Taxon(
            id=_slug(query) or "unknown",
            scientific_name=query,
            common_name=query,
            cultivar=None,
            category=category,
            source="manual",
        )
