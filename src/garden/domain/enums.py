from enum import StrEnum


class LocationKind(StrEnum):
    IN_GROUND = "in_ground"
    RAISED_BED = "raised_bed"
    CONTAINER = "container"
    GREENHOUSE = "greenhouse"
    HYDROPONIC = "hydroponic"
    INDOOR = "indoor"
    SEED_TRAY = "seed_tray"
    FLOWER_POT = "flower_pot"


# Location kinds with no exposure to outdoor weather. Plants here don't get
# fetched weather, don't accumulate GDD or rain, and don't get water/frost
# recommendations — the gardener controls their light and water directly
# (e.g. a seed tray under a grow light).
INDOOR_LOCATION_KINDS = frozenset({LocationKind.INDOOR, LocationKind.SEED_TRAY})


# Location kinds that drain/leach faster than in-ground beds. The
# care-profile engine applies a per-profile `container_multiplier` to
# water + fertilizer cadences for plants in any of these.
CONTAINER_LOCATION_KINDS = frozenset({
    LocationKind.CONTAINER,
    LocationKind.INDOOR,
    LocationKind.SEED_TRAY,
    LocationKind.FLOWER_POT,
})


class PlantStatus(StrEnum):
    """Lifecycle phase of a plant.

    "Is this plant still in the garden?" is answered by `Plant.terminal_at is None`,
    NOT by checking against any status value here. `DEAD` and `REMOVED` exist for
    legacy rows that predate the `terminal_at` column.
    """

    SEEDED = "seeded"
    GERMINATED = "germinated"
    TRANSPLANTED = "transplanted"
    GROWING = "growing"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    HARVESTED = "harvested"
    DORMANT = "dormant"
    DEAD = "dead"  # legacy — read terminal_at instead
    REMOVED = "removed"  # legacy — read terminal_at instead


class AmendmentUnit(StrEnum):
    """Units for soil amendments and fertilizers.

    Mass units convert directly to kg. Volume units convert to L, then to mass
    via the amendment's bulk density (which is required for nutrient math on
    volume entries).
    """

    # mass
    KG = "kg"
    G = "g"
    LB = "lb"
    OZ = "oz"
    # volume — coarse
    L = "L"
    ML = "ml"
    GAL = "gal"
    FL_OZ = "fl-oz"
    CU_FT = "cu-ft"
    CU_YD = "cu-yd"
    # volume — small (liquid fertilizers)
    TSP = "tsp"
    TBSP = "tbsp"
    CUP = "cup"


class MetricKind(StrEnum):
    """Controlled vocabulary for `Observation.metric`.

    The DB column stays a free string so legacy and ad-hoc metrics keep
    working, but new code should use these enum values. Renderers (the
    website's weather charts, the GDD service) compare against `.value`,
    so adding a new metric here is the only place a name needs to change.
    """

    RAIN_MM = "rain_mm"
    TEMP_C_MEAN = "temp_c_mean"
    TEMP_C_MIN = "temp_c_min"
    TEMP_C_MAX = "temp_c_max"
    SUNSHINE_HOURS = "sunshine_hours"
    SOIL_MOISTURE_PCT = "soil_moisture_pct"
    HEIGHT_CM = "height_cm"


class EventType(StrEnum):
    SEEDED = "seeded"
    GERMINATED = "germinated"
    TRANSPLANTED = "transplanted"
    WATERED = "watered"
    FERTILIZED = "fertilized"
    PRUNED = "pruned"
    STAKED = "staked"  # tied / trellised / supported
    POLLINATED = "pollinated"  # hand-pollination
    CHECKED = "checked"  # I looked at it and nothing else to log
    HARVESTED = "harvested"
    TREATED = "treated"  # pest/disease treatment
    AMENDED = "amended"  # soil amendment (bed-scoped)
    OBSERVED = "observed"  # narrative note; structured data goes in Observation
    DIED = "died"
    REMOVED = "removed"
