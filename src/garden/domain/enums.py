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
