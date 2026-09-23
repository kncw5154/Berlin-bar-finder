"""
geodienste.py – Externe OSM-Dienste und Geo-Berechnungen für den Berlin Bar Finder.

- Adresssuche (Geocoding) über Nominatim
- Fußweg-Routing über den OSRM-Server der FOSSGIS (routing.openstreetmap.de)
- Luftlinienentfernung per Haversine-Formel
"""

import numpy as np
import requests

USER_AGENT = "BerlinBarFinder/1.0 (BHT Berlin, GIS-Gelaendepraktikum)"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Wichtig: Der Pfad "routed-foot" wählt das Fußgänger-Profil. Ohne dieses Präfix
# liefert der öffentliche Server Autorouten.
ROUTING_URL = "https://routing.openstreetmap.de/routed-foot/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"

# Grobe Umgebung von Berlin (links, oben, rechts, unten) – begrenzt die Adresssuche
BERLIN_VIEWBOX = "13.08,52.68,13.77,52.33"


def adresse_suchen(text):
    """Sucht eine Adresse in Berlin. Rückgabe: (lat, lon, Anzeigename) oder None."""
    antwort = requests.get(
        NOMINATIM_URL,
        params={
            "q": text,
            "format": "jsonv2",
            "limit": 1,
            "viewbox": BERLIN_VIEWBOX,
            "bounded": 1,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    antwort.raise_for_status()
    treffer = antwort.json()
    if not treffer:
        return None
    t = treffer[0]
    return float(t["lat"]), float(t["lon"]), t.get("display_name", text)


def fussweg(start, ziel):
    """
    Berechnet einen Fußweg zwischen zwei Punkten (jeweils (lat, lon)).
    Rückgabe: dict mit 'linie' [[lat, lon], ...], 'meter', 'minuten' – oder None.
    """
    url = ROUTING_URL.format(lat1=start[0], lon1=start[1], lat2=ziel[0], lon2=ziel[1])
    antwort = requests.get(
        url,
        params={"overview": "full", "geometries": "geojson"},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    antwort.raise_for_status()
    daten = antwort.json()
    if daten.get("code") != "Ok" or not daten.get("routes"):
        return None
    route = daten["routes"][0]
    # GeoJSON speichert [lon, lat] – Folium erwartet [lat, lon], also umdrehen
    linie = [[lat, lon] for lon, lat in route["geometry"]["coordinates"]]
    return {"linie": linie, "meter": route["distance"], "minuten": route["duration"] / 60}


def osm_routen_link(start, ziel):
    """Link, der dieselbe Fußroute auf openstreetmap.org öffnet (Rückfalloption)."""
    return (
        "https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot"
        f"&route={start[0]:.6f}%2C{start[1]:.6f}%3B{ziel[0]:.6f}%2C{ziel[1]:.6f}"
    )


def entfernung_m(lat, lon, lats, lons):
    """Luftlinie in Metern von einem Punkt zu vielen Punkten (Haversine-Formel)."""
    r = 6_371_000  # mittlerer Erdradius in m
    phi1, phi2 = np.radians(lat), np.radians(lats)
    dphi = phi2 - phi1
    dlmb = np.radians(lons) - np.radians(lon)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))
