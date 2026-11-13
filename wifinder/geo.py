"""Conversão entre lat/lon e metros locais (aproximação plana, boa para poucos km)."""

import math

R = 6371000.0


def to_local(lat, lon, lat0, lon0):
    """Retorna (x leste, y norte) em metros. Aceita floats ou arrays numpy."""
    x = (lon - lon0) * math.pi / 180 * R * math.cos(math.radians(lat0))
    y = (lat - lat0) * math.pi / 180 * R
    return x, y


def to_geo(x, y, lat0, lon0):
    lat = lat0 + y / R * 180 / math.pi
    lon = lon0 + x / (R * math.cos(math.radians(lat0))) * 180 / math.pi
    return lat, lon
