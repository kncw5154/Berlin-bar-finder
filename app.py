"""
app.py – Berlin Bar Finder (GIS-Geländepraktikum, BHT Berlin)

Start lokal:  streamlit run app.py
"""

from html import escape

import folium
import pandas as pd
import requests
import streamlit as st
from folium.plugins import HeatMap, MarkerCluster
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

from geodienste import adresse_suchen, entfernung_m, fussweg, osm_routen_link
from overpass import BEZIRKE, TYPEN, hole_daten, hole_grenze

st.set_page_config(page_title="Berlin Bar Finder", page_icon="🍸", layout="wide")

# Darstellung je Typ: Emoji + Neonfarbe
STIL = {
    "Bar":  {"emoji": "🍸", "farbe": "#ff4b9b"},
    "Pub":  {"emoji": "🍺", "farbe": "#ffb000"},
    "Club": {"emoji": "🎵", "farbe": "#8a5cff"},
}

# OSM-Kacheln per CSS-Filter dunkel einfärben (kein API-Key nötig)
DARK_MAP_CSS = """<style>
.leaflet-tile-pane { filter: invert(1) hue-rotate(180deg) brightness(0.95) contrast(0.9); }
.leaflet-container { background: #0e1117; }
</style>"""


# ---------- Zwischengespeicherte Abfragen (schonen die öffentlichen OSM-Dienste) ----------
@st.cache_data(ttl=3600, show_spinner=False)
def lade(bezirk):
    return hole_daten(None if bezirk == "Ganz Berlin" else bezirk)


@st.cache_data(ttl=86400, show_spinner=False)
def lade_grenze(bezirk):
    return hole_grenze(bezirk)


@st.cache_data(ttl=86400, show_spinner=False)
def suche_adresse(text):
    return adresse_suchen(text)


@st.cache_data(ttl=3600, show_spinner=False)
def route(start, ziel):
    return fussweg(start, ziel)


def fmt_meter(m):
    return f"{m:.0f} m" if m < 1000 else f"{m / 1000:.1f} km".replace(".", ",")


# ======================= SEITENLEISTE =======================
st.sidebar.title("🍸 Bar Finder")

modus = st.sidebar.radio("Suchmodus", ["📍 In meiner Nähe", "🗺️ Nach Bezirk"], horizontal=True)

standort = None      # (lat, lon) des Nutzers, falls bekannt
standort_text = ""
bezirk = "Ganz Berlin"

if modus == "📍 In meiner Nähe":
    quelle = st.sidebar.radio("Standort", ["GPS (Browser)", "Adresse eingeben"], horizontal=True)
    if quelle == "GPS (Browser)":
        pos = get_geolocation()
        if pos is None:
            st.sidebar.info("Warte auf Standortfreigabe im Browser …")
        elif "error" in pos:
            st.sidebar.warning("Standort nicht verfügbar (Freigabe verweigert oder kein GPS). "
                               "Bitte „Adresse eingeben“ verwenden.")
        else:
            standort = (pos["coords"]["latitude"], pos["coords"]["longitude"])
            standort_text = f"GPS (± {pos['coords'].get('accuracy', 0):.0f} m)"
    else:
        adresse = st.sidebar.text_input("Adresse oder Ort in Berlin", "Alexanderplatz")
        if adresse.strip():
            try:
                treffer = suche_adresse(adresse.strip())
            except requests.RequestException:
                treffer = None
                st.sidebar.error("Adresssuche gerade nicht erreichbar.")
            if treffer:
                standort = (treffer[0], treffer[1])
                standort_text = treffer[2]
            else:
                st.sidebar.warning("Adresse in Berlin nicht gefunden.")
    radius = st.sidebar.slider("Umkreis (m)", 250, 3000, 1000, step=250)
else:
    bezirk = st.sidebar.selectbox("Bezirk", ["Ganz Berlin"] + BEZIRKE, index=6)

st.sidebar.markdown("---")
suche = st.sidebar.text_input("🔍 Name suchen", placeholder="z. B. Kneipe, Späti …")
typen = st.sidebar.multiselect("Art", list(TYPEN.values()), default=list(TYPEN.values()))
nur_aussen = st.sidebar.checkbox("☀️ Nur mit Außensitzplätzen")
nur_zeiten = st.sidebar.checkbox("🕒 Nur mit eingetragenen Öffnungszeiten")
ansicht = st.sidebar.radio("Kartenansicht", ["Marker", "Heatmap"], horizontal=True)

st.sidebar.markdown("---")
st.sidebar.markdown(" · ".join(f"{s['emoji']} {t}" for t, s in STIL.items()))
st.sidebar.caption(
    "Daten: © [OpenStreetMap-Mitwirkende](https://www.openstreetmap.org/copyright) (ODbL) · "
    "Abfrage: Overpass API · Adresssuche: Nominatim · Routing: OSRM (FOSSGIS) · "
    "[Kartenfehler melden](https://www.openstreetmap.org/fixthemap)"
)

# ======================= DATEN =======================
st.title("🍸 Berlin Bar Finder")
st.caption("Bars, Pubs und Clubs in Berlin – live aus OpenStreetMap")

try:
    with st.spinner("Lade Daten aus OpenStreetMap …"):
        df = lade(bezirk)
except requests.RequestException as fehler:
    st.error(f"Die Overpass API ist gerade nicht erreichbar oder überlastet. "
             f"Bitte in einer Minute erneut versuchen.\n\nDetails: {fehler}")
    st.stop()

if df.empty:
    st.warning("Für diese Auswahl wurden keine Daten gefunden.")
    st.stop()

# Suchgebiet festlegen: Umkreis um den Standort oder der gewählte Bezirk
naehe_modus = modus == "📍 In meiner Nähe"
if naehe_modus:
    if standort is None:
        st.info("👈 Bitte links den Standort freigeben oder eine Adresse eingeben.")
        st.stop()
    df = df.assign(entfernung=entfernung_m(standort[0], standort[1], df["lat"].values, df["lon"].values))
    gebiet = df[df["entfernung"] <= radius].sort_values("entfernung")
else:
    gebiet = df

# Filter anwenden
gefiltert = gebiet[gebiet["typ"].isin(typen)]
if suche.strip():
    gefiltert = gefiltert[gefiltert["name"].str.contains(suche.strip(), case=False, regex=False)]
if nur_aussen:
    gefiltert = gefiltert[gefiltert["aussenbereich"]]
if nur_zeiten:
    gefiltert = gefiltert[gefiltert["oeffnungszeiten"] != ""]

# ======================= KENNZAHLEN =======================
k = st.columns(4)
k[0].metric("Treffer", len(gefiltert))
k[1].metric("mit Außenbereich", int(gefiltert["aussenbereich"].sum()))
anteil = (gefiltert["oeffnungszeiten"] != "").mean() * 100 if len(gefiltert) else 0
k[2].metric("mit Öffnungszeiten in OSM", f"{anteil:.0f} %")
if naehe_modus and len(gefiltert):
    k[3].metric("Nächster Treffer", fmt_meter(gefiltert["entfernung"].iloc[0]))
else:
    k[3].metric("Gebiet", bezirk)

if naehe_modus:
    st.caption(f"📍 Standort: {standort_text} · Umkreis {fmt_meter(radius)}")

tab_karte, tab_statistik, tab_tabelle = st.tabs(["🗺️ Karte", "📊 Statistik", "📋 Tabelle"])


# ======================= KARTE =======================
def popup_html(z):
    osm_link = f"https://www.openstreetmap.org/{z.osm_typ}/{z.osm_id}"
    edit_link = f"https://www.openstreetmap.org/edit?{z.osm_typ}={z.osm_id}"
    note_link = f"https://www.openstreetmap.org/note/new#map=19/{z.lat}/{z.lon}"
    teile = [f"<b>{STIL.get(z.typ, {}).get('emoji', '')} {escape(z.name)}</b> <i>({z.typ})</i>"]
    if naehe_modus:
        teile.append(f"🚶 {fmt_meter(z.entfernung)} Luftlinie")
    if z.adresse:
        teile.append(escape(z.adresse))
    teile.append("🕒 " + (escape(z.oeffnungszeiten) if z.oeffnungszeiten else "Öffnungszeiten unbekannt"))
    if z.aussenbereich:
        teile.append("☀️ Außensitzplätze")
    if z.website:
        teile.append(f'<a href="{escape(z.website)}" target="_blank">Website</a>')
    teile.append(
        f'<a href="{osm_link}" target="_blank">In OSM ansehen</a> · '
        f'<a href="{edit_link}" target="_blank">Bearbeiten</a> · '
        f'<a href="{note_link}" target="_blank">Fehler melden</a>'
    )
    return "<br>".join(teile)


def icon(typ):
    s = STIL.get(typ, {"emoji": "📍", "farbe": "#aaaaaa"})
    return folium.DivIcon(
        html=(f'<div style="font-size:17px;width:30px;height:30px;border-radius:50%;'
              f'background:#1a1d29;border:2px solid {s["farbe"]};box-shadow:0 0 8px {s["farbe"]};'
              f'display:flex;align-items:center;justify-content:center;">{s["emoji"]}</div>'),
        icon_size=(30, 30), icon_anchor=(15, 15),
    )


with tab_karte:
    # Routenauswahl (nur im Nähe-Modus)
    route_daten, ziel = None, None
    if naehe_modus and len(gefiltert):
        kandidaten = gefiltert.head(30)
        optionen = ["– keine Route –"] + [
            f"{z.name} ({fmt_meter(z.entfernung)})" for z in kandidaten.itertuples()
        ]
        wahl = st.selectbox("🧭 Fußweg anzeigen zu …", optionen)
        if wahl != optionen[0]:
            z = kandidaten.iloc[optionen.index(wahl) - 1]
            ziel = (z["lat"], z["lon"])
            try:
                with st.spinner("Berechne Fußweg …"):
                    route_daten = route(standort, ziel)
            except requests.RequestException:
                route_daten = None
            if route_daten:
                r1, r2, r3 = st.columns([1, 1, 2])
                r1.metric("Strecke", fmt_meter(route_daten["meter"]))
                r2.metric("Gehzeit", f"{route_daten['minuten']:.0f} min")
                r3.markdown(f"<br>[Route auf openstreetmap.org öffnen ↗]({osm_routen_link(standort, ziel)})",
                            unsafe_allow_html=True)
            else:
                st.warning("Routing-Dienst gerade nicht erreichbar.")
                st.markdown(f"[Route stattdessen auf openstreetmap.org öffnen ↗]({osm_routen_link(standort, ziel)})")

    # Kartenmittelpunkt und Zoom
    if naehe_modus:
        mitte = standort
        zoom = 16 if radius <= 500 else 15 if radius <= 1000 else 14 if radius <= 2000 else 13
    elif len(gefiltert):
        mitte = (gefiltert["lat"].mean(), gefiltert["lon"].mean())
        zoom = 11 if bezirk == "Ganz Berlin" else 13
    else:
        mitte, zoom = (52.52, 13.405), 11

    karte = folium.Map(location=mitte, zoom_start=zoom, tiles="OpenStreetMap")
    karte.get_root().header.add_child(folium.Element(DARK_MAP_CSS))

    # Bezirksgrenze
    if not naehe_modus and bezirk != "Ganz Berlin":
        try:
            for linie in lade_grenze(bezirk):
                folium.PolyLine(linie, color="#00e5ff", weight=3, opacity=0.8).add_to(karte)
        except requests.RequestException:
            pass  # Grenze ist nur Zusatz – bei Fehler einfach weglassen

    # Standort + Umkreis
    if naehe_modus:
        folium.Circle(standort, radius=radius, color="#00e5ff", weight=1.5,
                      fill=True, fill_opacity=0.06).add_to(karte)
        folium.CircleMarker(standort, radius=8, color="white", weight=2, fill=True,
                            fill_color="#1e90ff", fill_opacity=1, tooltip="Dein Standort").add_to(karte)

    # Route
    if route_daten:
        folium.PolyLine(route_daten["linie"], color="#00e5ff", weight=5, opacity=0.9,
                        tooltip=f"{fmt_meter(route_daten['meter'])} · {route_daten['minuten']:.0f} min").add_to(karte)

    # Lokale: Marker oder Heatmap
    if ansicht == "Heatmap":
        if len(gefiltert):
            HeatMap(gefiltert[["lat", "lon"]].values.tolist(), radius=18, blur=15).add_to(karte)
    else:
        ziel_gruppe = MarkerCluster(options={"disableClusteringAtZoom": 16}).add_to(karte)
        for z in gefiltert.itertuples():
            folium.Marker(
                location=[z.lat, z.lon],
                popup=folium.Popup(popup_html(z), max_width=300),
                tooltip=z.name,
                icon=icon(z.typ),
            ).add_to(ziel_gruppe)

    if gefiltert.empty:
        st.info("Keine Treffer mit diesen Filtern.")
    st_folium(karte, height=620, use_container_width=True, returned_objects=[], key="karte")

# ======================= STATISTIK =======================
with tab_statistik:
    st.subheader("Verteilung nach Art")
    st.caption("Grundlage: alle Treffer im Suchgebiet, ohne weitere Filter")
    verteilung = gebiet["typ"].value_counts().reindex(list(TYPEN.values()), fill_value=0)
    st.bar_chart(verteilung, horizontal=True, color="#ff4b9b")

    st.subheader("Datenvollständigkeit in OpenStreetMap")
    st.caption("Wie viel Prozent der Lokale haben das jeweilige Merkmal in OSM eingetragen? "
               "Niedrige Werte zeigen, wo Mapping-Bedarf besteht.")
    if len(gebiet):
        vollstaendig = pd.Series({
            "Name": gebiet["hat_name"].mean() * 100,
            "Adresse": gebiet["hat_adresse"].mean() * 100,
            "Öffnungszeiten": (gebiet["oeffnungszeiten"] != "").mean() * 100,
            "Website": (gebiet["website"] != "").mean() * 100,
            "Außensitzplätze (ja/nein)": gebiet["hat_aussen_angabe"].mean() * 100,
        }).round(1)
        st.bar_chart(vollstaendig, horizontal=True, color="#00e5ff")

# ======================= TABELLE =======================
with tab_tabelle:
    spalten = ["name", "typ", "adresse", "oeffnungszeiten", "aussenbereich", "website"]
    anzeige = gefiltert[spalten].copy()
    if naehe_modus:
        anzeige.insert(2, "entfernung_m", gefiltert["entfernung"].round(0).astype(int))
    st.dataframe(anzeige, hide_index=True)
    st.download_button(
        "⬇️ Als CSV herunterladen",
        anzeige.to_csv(index=False).encode("utf-8"),
        file_name="bar_finder_auswahl.csv",
        mime="text/csv",
    )
