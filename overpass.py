"""
overpass.py – Datenabfrage für den Berlin Bar Finder.

Fragt Bars, Pubs und Clubs (OSM-Tag amenity=bar/pub/nightclub) live über die
Overpass API ab und wandelt das Ergebnis in eine pandas-Tabelle um.
"""

import requests
import pandas as pd

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Die 12 Berliner Bezirke (in OSM: boundary=administrative, admin_level=9)
BEZIRKE = [
    "Charlottenburg-Wilmersdorf",
    "Friedrichshain-Kreuzberg",
    "Lichtenberg",
    "Marzahn-Hellersdorf",
    "Mitte",
    "Neukölln",
    "Pankow",
    "Reinickendorf",
    "Spandau",
    "Steglitz-Zehlendorf",
    "Tempelhof-Schöneberg",
    "Treptow-Köpenick",
]

# OSM-Wert -> Anzeigename
TYPEN = {"bar": "Bar", "pub": "Pub", "nightclub": "Club"}


def baue_abfrage(bezirk=None):
    """Erzeugt die Overpass-QL-Abfrage für einen Bezirk oder ganz Berlin (bezirk=None)."""
    if bezirk is None:
        gebiet = 'area["name"="Berlin"]["boundary"="administrative"]["admin_level"="4"]->.gebiet;'
    else:
        # Erst Berlin als Suchraum, darin die Bezirksgrenze suchen und in eine Fläche umwandeln.
        # So wird z. B. "Mitte" nicht mit gleichnamigen Gebieten in anderen Städten verwechselt.
        gebiet = (
            'area["name"="Berlin"]["boundary"="administrative"]["admin_level"="4"]->.berlin;\n'
            f'rel(area.berlin)["boundary"="administrative"]["admin_level"="9"]["name"="{bezirk}"];\n'
            "map_to_area->.gebiet;"
        )

    return f"""[out:json][timeout:90];
{gebiet}
nwr["amenity"~"^(bar|pub|nightclub)$"](area.gebiet);
out center tags;"""


def hole_rohdaten(bezirk=None):
    """Schickt die Abfrage an Overpass und gibt die Liste der OSM-Elemente zurück."""
    antwort = requests.post(
        OVERPASS_URL,
        data={"data": baue_abfrage(bezirk)},
        headers={"User-Agent": "BerlinBarFinder/1.0 (BHT Berlin, GIS-Gelaendepraktikum)"},
        timeout=120,
    )
    antwort.raise_for_status()  # löst bei HTTP-Fehlern (z. B. 429, 504) eine Exception aus
    return antwort.json().get("elements", [])


def in_tabelle(elemente):
    """Wandelt die Overpass-Elemente in einen DataFrame mit einer Zeile pro Lokal um."""
    zeilen = []
    for el in elemente:
        tags = el.get("tags", {})

        # Nodes haben lat/lon direkt, Ways/Relations (z. B. Clubgebäude) über "out center"
        if "lat" in el:
            lat, lon = el["lat"], el["lon"]
        elif "center" in el:
            lat, lon = el["center"]["lat"], el["center"]["lon"]
        else:
            continue  # ohne Koordinate nicht darstellbar

        strasse = " ".join(
            teil for teil in [tags.get("addr:street", ""), tags.get("addr:housenumber", "")] if teil
        )
        adresse = ", ".join(
            teil for teil in [strasse, " ".join(
                t for t in [tags.get("addr:postcode", ""), tags.get("addr:city", "")] if t
            )] if teil
        )

        zeilen.append({
            "osm_typ": el["type"],          # node / way / relation
            "osm_id": el["id"],
            "lat": lat,
            "lon": lon,
            "name": tags.get("name", "(ohne Namen)"),
            "typ": TYPEN.get(tags.get("amenity"), tags.get("amenity")),
            "adresse": adresse,
            "oeffnungszeiten": tags.get("opening_hours", ""),
            "website": tags.get("website", tags.get("contact:website", "")),
            "aussenbereich": tags.get("outdoor_seating") == "yes",
            # für die Statistik: ist das Merkmal in OSM überhaupt erfasst?
            "hat_name": "name" in tags,
            "hat_adresse": "addr:street" in tags,
            "hat_aussen_angabe": "outdoor_seating" in tags,
        })

    return pd.DataFrame(zeilen)


def hole_grenze(bezirk):
    """
    Holt die Grenze eines Bezirks als Liste von Linien ([[lat, lon], ...]).
    Es werden einfach alle Außenlinien der Grenz-Relation gezeichnet – dafür
    müssen die Teilstücke nicht zu einem Polygon zusammengesetzt werden.
    """
    abfrage = f"""[out:json][timeout:60];
area["name"="Berlin"]["boundary"="administrative"]["admin_level"="4"]->.berlin;
rel(area.berlin)["boundary"="administrative"]["admin_level"="9"]["name"="{bezirk}"];
out geom;"""
    antwort = requests.post(
        OVERPASS_URL,
        data={"data": abfrage},
        headers={"User-Agent": "BerlinBarFinder/1.0 (BHT Berlin, GIS-Gelaendepraktikum)"},
        timeout=90,
    )
    antwort.raise_for_status()
    linien = []
    for rel in antwort.json().get("elements", []):
        for mitglied in rel.get("members", []):
            if mitglied.get("type") == "way" and mitglied.get("role") in ("outer", "") and "geometry" in mitglied:
                linien.append([[p["lat"], p["lon"]] for p in mitglied["geometry"]])
    return linien


def hole_daten(bezirk=None):
    """Komplette Pipeline: Abfrage -> Tabelle."""
    return in_tabelle(hole_rohdaten(bezirk))
