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


class PlantStatus(StrEnum):
    SEEDED = "seeded"
    GERMINATED = "germinated"
    TRANSPLANTED = "transplanted"
    GROWING = "growing"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    HARVESTED = "harvested"
    DORMANT = "dormant"
    DEAD = "dead"
    REMOVED = "removed"


# Terminal plant statuses — plants in one of these are no longer in the
# garden. They get no recommendations, refuse new events, and are hidden
# from current-state views (plants table, growth-stage tracker, …). Treat
# this as the single source of truth: prefer `p.status in TERMINAL_PLANT_STATUSES`
# over checking PlantStatus.DEAD directly, so adding a new terminal state later
# is a one-line change.
TERMINAL_PLANT_STATUSES = frozenset({PlantStatus.DEAD, PlantStatus.REMOVED})


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


class EventType(StrEnum):
    SEEDED = "seeded"
    GERMINATED = "germinated"
    TRANSPLANTED = "transplanted"
    WATERED = "watered"
    FERTILIZED = "fertilized"
    PRUNED = "pruned"
    HARVESTED = "harvested"
    TREATED = "treated"  # pest/disease treatment
    AMENDED = "amended"  # soil amendment (bed-scoped)
    OBSERVED = "observed"  # narrative note; structured data goes in Observation
    DIED = "died"
    REMOVED = "removed"
