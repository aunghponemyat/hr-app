from decimal import Decimal

import pytest
from geopy.distance import geodesic  # type: ignore[import-untyped]

from app.core.config import Settings
from app.core.errors import AppError
from app.models import WorkLocation
from app.services.gps_service import verify_onsite


def office(location_id: int = 1, radius: int = 100) -> WorkLocation:
    return WorkLocation(
        id=location_id,
        name="HQ",
        latitude=Decimal("13.756300"),
        longitude=Decimal("100.501800"),
        allowed_radius_m=radius,
    )


@pytest.mark.parametrize(
    "meters,allowed",
    [(30, True), (99, True), (99.999, True), (100.001, False), (101, False), (500, False)],
)
def test_geodesic_perimeter_uses_unrounded_distance(
    settings: Settings, meters: float, allowed: bool
) -> None:
    location = office()
    fix = geodesic(meters=meters).destination(
        (float(location.latitude), float(location.longitude)), bearing=0
    )
    if allowed:
        result = verify_onsite([location], fix.latitude, fix.longitude, 10, settings)
        assert result.verified and result.location_id == 1
        assert float(result.distance_m) == pytest.approx(meters, abs=0.01)
    else:
        with pytest.raises(AppError) as error:
            verify_onsite([location], fix.latitude, fix.longitude, 10, settings)
        assert error.value.status_code == 403 and error.value.code == "OUTSIDE_WORK_PERIMETER"
        assert error.value.details is not None and error.value.details["allowed_radius_m"] == 100


@pytest.mark.parametrize(
    "lat,lon,accuracy,code",
    [
        (None, 100, 10, "GPS_REQUIRED"),
        (13, None, 10, "GPS_REQUIRED"),
        (13, 100, None, "GPS_REQUIRED"),
        (91, 100, 10, "GPS_REQUIRED"),
        (-91, 100, 10, "GPS_REQUIRED"),
        (13, 181, 10, "GPS_REQUIRED"),
        (13, -181, 10, "GPS_REQUIRED"),
        (13, 100, -1, "GPS_REQUIRED"),
        (float("nan"), 100, 10, "GPS_REQUIRED"),
        (13, float("inf"), 10, "GPS_REQUIRED"),
        (13, 100, float("nan"), "GPS_REQUIRED"),
        (13, 100, 100.01, "LOW_GPS_ACCURACY"),
    ],
)
def test_gps_fix_validation(
    settings: Settings, lat: float | None, lon: float | None, accuracy: float | None, code: str
) -> None:
    with pytest.raises(AppError) as error:
        verify_onsite([office()], lat, lon, accuracy, settings)
    assert error.value.code == code and error.value.status_code == 422


def test_missing_locations_and_accuracy_threshold(settings: Settings) -> None:
    with pytest.raises(AppError) as error:
        verify_onsite([], 13, 100, 10, settings)
    assert error.value.code == "NO_WORK_LOCATION_CONFIGURED"
    assert verify_onsite([office()], 13.7563, 100.5018, 100, settings).verified


def test_nearest_location_radius_is_authoritative_and_ties_are_deterministic(
    settings: Settings,
) -> None:
    closer = WorkLocation(
        id=1, name="Near", latitude=Decimal("0"), longitude=Decimal("0"), allowed_radius_m=50
    )
    farther = WorkLocation(
        id=2, name="Far", latitude=Decimal("0.001100"), longitude=Decimal("0"), allowed_radius_m=100
    )
    with pytest.raises(AppError) as error:
        verify_onsite([farther, closer], 0.0005, 0, 10, settings)
    assert error.value.code == "OUTSIDE_WORK_PERIMETER"
    assert error.value.details is not None and error.value.details["allowed_radius_m"] == 50
    assert verify_onsite([office(2), office(1)], 13.7563, 100.5018, 0, settings).location_id == 1
