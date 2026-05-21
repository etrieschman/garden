from garden.config.yaml_config import BedConfig, GardenConfig
from garden.services.sync import sync_config_to_storage
from garden.storage.sqlite import SQLiteStorage


def test_yaml_beds_upsert_into_db(storage: SQLiteStorage) -> None:
    cfg = GardenConfig(
        name="Test",
        default_lat=42.0,
        default_lon=-71.0,
        beds=[
            BedConfig(
                id="patio-north",
                kind="raised_bed",
                dimensions={"length_cm": 240, "width_cm": 120, "depth_cm": 30},
                substrate={"medium": "Coast of Maine raised bed mix"},
            )
        ],
    )

    assert sync_config_to_storage(cfg, storage) == 1
    loaded = storage.get_location("patio-north")
    assert loaded is not None
    assert loaded.lat == 42.0  # inherited from default_lat
    assert loaded.dimensions is not None and loaded.dimensions.area_m2 == 2.88
    assert loaded.substrate is not None
    assert loaded.substrate.medium == "Coast of Maine raised bed mix"


def test_sync_is_idempotent_and_updates_on_change(storage: SQLiteStorage) -> None:
    cfg = GardenConfig(
        beds=[BedConfig(id="bed-a", kind="raised_bed", lat=1.0, lon=2.0)]
    )
    sync_config_to_storage(cfg, storage)
    sync_config_to_storage(cfg, storage)  # idempotent
    assert len(storage.list_locations()) == 1

    # Edit the bed's substrate in yaml — DB picks it up next sync
    cfg.beds[0].substrate = {"medium": "compost mix"}
    sync_config_to_storage(cfg, storage)
    loc = storage.get_location("bed-a")
    assert loc is not None and loc.substrate is not None
    assert loc.substrate.medium == "compost mix"


def test_removing_bed_from_yaml_does_not_delete_from_db(storage: SQLiteStorage) -> None:
    cfg = GardenConfig(beds=[BedConfig(id="bed-a", kind="raised_bed")])
    sync_config_to_storage(cfg, storage)

    # Remove from yaml
    cfg.beds = []
    sync_config_to_storage(cfg, storage)

    # Still in DB — history would otherwise dangle
    assert storage.get_location("bed-a") is not None
