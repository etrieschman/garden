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
