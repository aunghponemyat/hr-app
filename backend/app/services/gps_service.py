from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite

from geopy.distance import geodesic  # type: ignore[import-untyped]

from app.core.config import Settings
from app.core.errors import AppError
from app.models import WorkLocation


@dataclass(frozen=True)
class GpsResult:
    location_id: int
    distance_m: Decimal
    verified: bool = True


def verify_onsite(
    team_locations: Sequence[WorkLocation],
    latitude: float | None,
    longitude: float | None,
    accuracy_m: float | None,
    settings: Settings,
) -> GpsResult:
    if (
        latitude is None
        or longitude is None
        or accuracy_m is None
        or not all(isfinite(value) for value in (latitude, longitude, accuracy_m))
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or accuracy_m < 0
    ):
        raise AppError(422, "GPS_REQUIRED", "Provide valid latitude, longitude, and GPS accuracy.")
    if accuracy_m > settings.max_gps_accuracy_m:
        raise AppError(
            422, "LOW_GPS_ACCURACY", "GPS accuracy is too low. Retry outdoors or near a window."
        )
    if not team_locations:
        raise AppError(
            422, "NO_WORK_LOCATION_CONFIGURED", "No work location is configured for your team."
        )
    distance, nearest = min(
        (
            (
                geodesic(
                    (latitude, longitude), (float(location.latitude), float(location.longitude))
                ).meters,
                location,
            )
            for location in team_locations
        ),
        key=lambda item: (item[0], item[1].id),
    )
    rounded = Decimal(str(distance)).quantize(Decimal("0.01"))
    if distance > nearest.allowed_radius_m:
        raise AppError(
            403,
            "OUTSIDE_WORK_PERIMETER",
            f"You are {distance:.0f} m from the office.",
            details={"distance_m": float(rounded), "allowed_radius_m": nearest.allowed_radius_m},
        )
    return GpsResult(location_id=nearest.id, distance_m=rounded)
