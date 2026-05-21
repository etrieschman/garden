from garden.domain import Dimensions, LocationKind, Substrate, Taxon
from garden.domain.location import Location


def test_dimensions_area_volume() -> None:
    d = Dimensions(length_cm=240, width_cm=120, depth_cm=30)
    assert d.area_m2 == 2.88
    assert d.volume_l is not None and abs(d.volume_l - 864.0) < 1e-6


def test_dimensions_diameter_round_container() -> None:
    d = Dimensions(diameter_cm=40, depth_cm=30)
    assert d.area_m2 is not None and abs(d.area_m2 - 0.12566) < 1e-3
    assert d.volume_l is not None


def test_taxon_display_name() -> None:
    assert Taxon(
        id="t", scientific_name="Solanum lycopersicum",
        common_name="Tomato", cultivar="Garden Gem",
    ).display_name == "Tomato 'Garden Gem'"


def test_location_serializes_with_substrate() -> None:
    loc = Location(
        id="patio-north",
        name="Patio raised bed (north)",
        kind=LocationKind.RAISED_BED,
        lat=42.3736,
        lon=-71.1034,
        dimensions=Dimensions(length_cm=240, width_cm=120, depth_cm=30),
        substrate=Substrate(medium="Coast of Maine raised bed mix"),
    )
    dumped = loc.model_dump(mode="json")
    assert dumped["dimensions"]["length_cm"] == 240
    assert dumped["substrate"]["medium"] == "Coast of Maine raised bed mix"
