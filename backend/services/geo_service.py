"""Geo service — Haversine distance and coordinate/radius validation.

Pure functions only: no I/O, fully unit-testable.

NOTE ON SCOPE: the Haversine formula computes great-circle distance between
two known points. It does NOT discover grounds by itself — grounds/lobbies
come from our database; Haversine only ranks/filters them by distance.
Verified ground data can later be imported from OpenStreetMap (Overpass API)
or other open geo sources into the `grounds` table.
"""
import math
from typing import List, Optional, Tuple

EARTH_RADIUS_KM = 6371.0088  # IUGG mean Earth radius

DEFAULT_RADIUS_KM = 10.0
MIN_RADIUS_KM = 0.5
MAX_RADIUS_KM = 100.0


class GeoValidationError(Exception):
    """Raised for invalid coordinates or radius."""


def validate_latitude(lat) -> float:
    try:
        lat = float(lat)
    except (TypeError, ValueError):
        raise GeoValidationError("Latitude must be a number.")
    if not (-90.0 <= lat <= 90.0) or math.isnan(lat):
        raise GeoValidationError("Latitude must be between -90 and 90.")
    return lat


def validate_longitude(lon) -> float:
    try:
        lon = float(lon)
    except (TypeError, ValueError):
        raise GeoValidationError("Longitude must be a number.")
    if not (-180.0 <= lon <= 180.0) or math.isnan(lon):
        raise GeoValidationError("Longitude must be between -180 and 180.")
    return lon


def validate_radius(radius_km) -> float:
    try:
        radius_km = float(radius_km)
    except (TypeError, ValueError):
        raise GeoValidationError("Radius must be a number of kilometres.")
    if math.isnan(radius_km) or not (MIN_RADIUS_KM <= radius_km <= MAX_RADIUS_KM):
        raise GeoValidationError(
            f"Radius must be between {MIN_RADIUS_KM} and {MAX_RADIUS_KM} km."
        )
    return radius_km


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two (lat, lon) points.

    Haversine formula:
        a = sin²(Δφ/2) + cos φ1 · cos φ2 · sin²(Δλ/2)
        c = 2 · atan2(√a, √(1−a))
        d = R · c
    where φ = latitude, λ = longitude (radians), R = Earth radius.
    """
    lat1, lon1, lat2, lon2 = map(
        math.radians, (validate_latitude(lat1), validate_longitude(lon1),
                       validate_latitude(lat2), validate_longitude(lon2))
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def filter_lobbies_by_distance(
    lobbies: List[dict],
    user_lat: float,
    user_lon: float,
    radius_km: float,
) -> List[Tuple[dict, float]]:
    """Return [(lobby, distance_km)] sorted nearest-first, within radius.

    Assumes lobbies already have 'latitude' and 'longitude' keys.
    """
    radius_km = validate_radius(radius_km)
    user_lat = validate_latitude(user_lat)
    user_lon = validate_longitude(user_lon)

    result: List[Tuple[dict, float]] = []
    for lobby in lobbies:
        try:
            d = haversine_distance_km(
                user_lat, user_lon, lobby["latitude"], lobby["longitude"]
            )
        except (GeoValidationError, KeyError, TypeError):
            continue  # skip malformed rows rather than failing the search
        if d <= radius_km:
            result.append((lobby, round(d, 2)))

    result.sort(key=lambda pair: pair[1])
    return result


def bounding_box(lat: float, lon: float, radius_km: float) -> dict:
    """Cheap pre-filter box (degrees) for DB-side filtering before the exact
    Haversine pass. Optional optimisation; correctness comes from Haversine.
    """
    lat = validate_latitude(lat)
    lon = validate_longitude(lon)
    radius_km = validate_radius(radius_km)

    dlat = radius_km / 111.32  # ~km per degree latitude
    dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 1e-9))
    return {
        "min_lat": lat - dlat,
        "max_lat": lat + dlat,
        "min_lon": lon - dlon,
        "max_lon": lon + dlon,
    }


def manual_coordinates(lat, lon) -> Tuple[float, float]:
    """Validate a manually entered coordinate pair."""
    return validate_latitude(lat), validate_longitude(lon)
