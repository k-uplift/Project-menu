"""좌표 변환 및 거리 계산.

서울 열린데이터광장 LOCALDATA 의 X/Y 는 GRS80 중부원점 TM (EPSG:5174).
실제 source vs naver 데이터로 검증 결과 2m 오차 — 변환 안정적.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Optional

from pyproj import Transformer

_TM_TO_WGS84 = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)

EARTH_RADIUS_M = 6_371_000


def tm_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """TM(EPSG:5174) (X, Y) → WGS84 (lng, lat)."""
    lng, lat = _TM_TO_WGS84.transform(x, y)
    return lng, lat


def parse_tm(x_raw: Optional[str], y_raw: Optional[str]) -> Optional[tuple[float, float]]:
    """문자열 형태의 TM (인허가 DB) → (lng, lat). 비어있으면 None."""
    if not x_raw or not y_raw:
        return None
    try:
        x = float(str(x_raw).strip())
        y = float(str(y_raw).strip())
    except ValueError:
        return None
    if x == 0 or y == 0:
        return None
    return tm_to_wgs84(x, y)


def haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """두 WGS84 좌표 사이 거리 (미터)."""
    dlng = radians(lng2 - lng1)
    dlat = radians(lat2 - lat1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))
