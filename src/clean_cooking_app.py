"""
CleanCook Streamlit App v3
===========================
Geolocation:
  - NO fallback. The user must confirm their school location before anything is plotted.
  - Nominatim returns up to 5 candidate results.
  - User picks the correct one from a list, or manually enters coordinates.
  - Only after confirmation does the map render and calculations proceed.

Requirements:
    pip install streamlit langchain langchain-openai langchain-tavily langgraph folium streamlit-folium requests

Run:
    export OPENAI_API_KEY=sk-...
    export TAVILY_API_KEY=tvly-...
    streamlit run cleancook_app.py
"""

import os
import json
import math
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

from langchain.tools import tool
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from dotenv import load_dotenv


load_dotenv()  # Load environment variables from .env file if present   


# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CleanCook — School Energy Transition",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
  html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

  .main-title  { font-family:'DM Serif Display',serif; font-size:2.4rem; color:#1a6b3c; line-height:1.2; margin-bottom:0; }
  .subtitle    { color:#666; font-size:1rem; margin-top:4px; }

  .metric-card { background:white; border:1px solid #ddd8cc; border-radius:12px; padding:18px 20px; text-align:center; box-shadow:0 2px 6px rgba(0,0,0,.04); }
  .metric-val  { font-family:'DM Serif Display',serif; font-size:1.8rem; color:#1a6b3c; }
  .metric-lbl  { font-size:0.78rem; color:#888; text-transform:uppercase; letter-spacing:.4px; }

  .section-head { font-family:'DM Serif Display',serif; font-size:1.3rem; color:#1c1c1c; border-bottom:2px solid #e8f5ee; padding-bottom:8px; margin-bottom:16px; }

  .candidate-card {
    background: white; border: 2px solid #ddd8cc; border-radius: 10px;
    padding: 14px 16px; margin-bottom: 10px; cursor: pointer;
    transition: border-color 0.2s;
  }
  .candidate-card:hover { border-color: #1a6b3c; }
  .candidate-card.selected { border-color: #1a6b3c; background: #e8f5ee; }
  .candidate-type { font-size:.75rem; color:#888; text-transform:uppercase; letter-spacing:.4px; }
  .candidate-name { font-size:.97rem; font-weight:600; color:#1c1c1c; }
  .candidate-addr { font-size:.82rem; color:#666; margin-top:2px; }
  .candidate-coord { font-size:.78rem; color:#1a6b3c; font-family:monospace; margin-top:4px; }

  .geo-confirmed { background:#e8f5ee; border:2px solid #1a6b3c; border-radius:10px; padding:12px 16px; font-size:.9rem; color:#1a4a2c; margin-bottom:12px; }
  .geo-pending   { background:#fdf3e7; border:2px solid #e07b2a; border-radius:10px; padding:12px 16px; font-size:.9rem; color:#7a4a1a; margin-bottom:12px; }
  .geo-search-hint { background:#f0f4ff; border:1px solid #b3c6f5; border-radius:8px; padding:10px 14px; font-size:.85rem; color:#2a3a7a; margin-bottom:12px; }

  .calc-step    { background:#f7f7f4; border-left:4px solid #1a6b3c; border-radius:0 10px 10px 0; padding:14px 18px; margin-bottom:12px; font-size:.93rem; line-height:1.7; }
  .calc-formula { background:#1c1c1c; color:#7ee8a2; border-radius:8px; padding:12px 16px; font-family:monospace; font-size:.9rem; margin:8px 0; white-space:pre; }
  .calc-example { background:#e8f5ee; border-radius:8px; padding:10px 14px; font-size:.88rem; color:#1a4a2c; margin:6px 0; }

  .dd-card   { background:#f7f7f4; border-left:4px solid #1a6b3c; border-radius:0 10px 10px 0; padding:14px 18px; margin-bottom:10px; font-size:.93rem; line-height:1.6; }
  .dd-source { font-size:.75rem; color:#888; margin-top:4px; }
  .warning-box { background:#fdf3e7; border-left:4px solid #e07b2a; border-radius:0 10px 10px 0; padding:12px 16px; font-size:.88rem; color:#7a4a1a; }

  .stButton > button { background:#1a6b3c !important; color:white !important; border-radius:8px !important; font-weight:600 !important; border:none !important; padding:10px 24px !important; }
  .stButton > button:hover { background:#2d9058 !important; }

  div[data-testid="stRadio"] label { cursor: pointer; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# NOMINATIM — returns multiple candidates, no fallback
# ─────────────────────────────────────────────────────────────
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS       = {"User-Agent": "CleanCookApp/3.0 (school-energy-transition-kenya)"}


@st.cache_data(show_spinner=False, ttl=3600)
def search_nominatim(query: str, limit: int = 5) -> list[dict]:
    """
    Search Nominatim for a place. Returns up to `limit` candidate results.
    Each result: {lat, lng, display_name, type, osm_type, importance}
    Returns empty list if nothing found — NO fallback.
    """
    try:
        params = {
            "q":            query,
            "format":       "json",
            "limit":        limit,
            "countrycodes": "ke",
            "addressdetails": 1,
        }
        resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        raw = resp.json()
        candidates = []
        for r in raw:
            addr = r.get("address", {})
            # Build a clean short label
            parts = [
                addr.get("amenity") or addr.get("building") or addr.get("tourism") or r.get("name", ""),
                addr.get("suburb") or addr.get("neighbourhood") or addr.get("village") or addr.get("town") or "",
                addr.get("county") or addr.get("state_district") or "",
            ]
            short_label = ", ".join(p for p in parts if p) or r.get("display_name", "")[:60]
            candidates.append({
                "lat":          float(r["lat"]),
                "lng":          float(r["lon"]),
                "display_name": r.get("display_name", ""),
                "short_label":  short_label,
                "type":         r.get("type", ""),
                "osm_type":     r.get("osm_type", ""),
                "importance":   r.get("importance", 0),
            })
        return candidates
    except Exception:
        return []


def offset_coords(lat: float, lng: float, d_km: float, bearing_deg: float):
    R = 6371
    b = math.radians(bearing_deg)
    lr = math.radians(lat)
    lat2 = math.asin(math.sin(lr)*math.cos(d_km/R) + math.cos(lr)*math.sin(d_km/R)*math.cos(b))
    lng2 = math.radians(lng) + math.atan2(
        math.sin(b)*math.sin(d_km/R)*math.cos(lr),
        math.cos(d_km/R) - math.sin(lr)*math.sin(lat2))
    return math.degrees(lat2), math.degrees(lng2)


# ─────────────────────────────────────────────────────────────
# CALCULATION ENGINE
# ─────────────────────────────────────────────────────────────
LITRES_PER_STUDENT_PER_MEAL = 5
POT_FILL_RATIO              = 0.80
REDUNDANCY_FACTOR           = 1.20
STOVE_COSTS  = {"LPG": {200:35_000,100:22_000,50:14_000}, "Electric":{200:55_000,100:38_000,50:22_000}}
POT_COSTS    = {200:28_000, 100:16_000, 50:9_000}
INFRA_COSTS  = {"LPG":18_000, "Electric":25_000}
INSTALL_RATE = {"LPG":0.15,   "Electric":0.20}


def calculate_sizing(n: int, m: int) -> dict:
    total = n * m * LITRES_PER_STUDENT_PER_MEAL
    alloc = {}; rem = total
    for sz in [200, 100, 50]:
        cnt = int(rem // (sz * POT_FILL_RATIO))
        if cnt > 0:
            alloc[sz] = cnt; rem -= cnt * sz * POT_FILL_RATIO
    if rem > 0:
        alloc[50] = alloc.get(50, 0) + 1
    tp = sum(alloc.values())
    return {"total_litres": total, "pot_alloc": alloc, "total_pots": tp,
            "stoves_needed": math.ceil(tp * REDUNDANCY_FACTOR)}


def calculate_costs(sizing: dict, fuel: str) -> dict:
    alloc = sizing["pot_alloc"]; stoves = sizing["stoves_needed"]; sc = STOVE_COSTS[fuel]
    stove_s = sum(sc[s]*c for s,c in alloc.items())
    pot_s   = sum(POT_COSTS[s]*c for s,c in alloc.items())
    infra_s = INFRA_COSTS[fuel]*stoves
    equip   = stove_s + infra_s
    inst    = int((equip + pot_s) * INSTALL_RATE[fuel])
    grand   = equip + pot_s + inst
    items = []
    for s,c in sorted(alloc.items(),reverse=True):
        lbl = "LPG burner" if fuel=="LPG" else "Induction cooker"
        items.append({"item":f"{c}× {lbl} ({s}L)","total":sc[s]*c})
    for s,c in sorted(alloc.items(),reverse=True):
        items.append({"item":f"{c}× Stainless pot ({s}L)","total":POT_COSTS[s]*c})
    items.append({"item":f"Infrastructure ({'cylinders+regulators' if fuel=='LPG' else '3-phase wiring'})","total":infra_s})
    items.append({"item":f"Installation ({int(INSTALL_RATE[fuel]*100)}%)","total":inst})
    return {"stove_s":stove_s,"pot_s":pot_s,"infra_s":infra_s,"equip":equip,"inst":inst,"grand":grand,"items":items}


# ─────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────
if "geo_confirmed" not in st.session_state:
    st.session_state.geo_confirmed = False   # Has user confirmed a location?
if "geo"           not in st.session_state:
    st.session_state.geo = None              # Confirmed geo dict
if "candidates"    not in st.session_state:
    st.session_state.candidates = []         # Search result candidates
if "search_query"  not in st.session_state:
    st.session_state.search_query = ""
if "chat_msgs"     not in st.session_state:
    st.session_state.chat_msgs = []


# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ API Keys")
    openai_key = st.text_input("OpenAI API Key", type="password",
                               value=os.environ.get("OPENAI_API_KEY",""))
    tavily_key = st.text_input("Tavily API Key", type="password",
                               value=os.environ.get("TAVILY_API_KEY",""))
    st.divider()

    st.markdown("### 🏫 School Details")
    school_name   = st.text_input("School Name", "Machakos High School")
    county        = st.text_input("County / Region", "Machakos County")
    num_students  = st.number_input("Number of Students", 10, 10000, 500, 10)
    meals_per_day = st.selectbox("Meals per Day", [1,2,3], index=2)
    fuel_type     = st.radio("Target Fuel Type", ["LPG","Electric"], horizontal=True)
    budget_kes    = st.number_input("Available Budget (KES)", 0, 50_000_000, 0, 10000)

    st.divider()

    # ── Geolocation section ──
    st.markdown("### 📍 School Geolocation")

    # Show confirmed status
    if st.session_state.geo_confirmed and st.session_state.geo:
        g = st.session_state.geo
        st.markdown(
            f'<div style="background:#e8f5ee;border:2px solid #1a6b3c;border-radius:8px;padding:10px 12px;font-size:.83rem;color:#1a4a2c">'
            f'✅ <b>Confirmed</b><br>'
            f'{g["display_name"][:65]}...<br>'
            f'<span style="font-family:monospace">{g["lat"]:.5f}, {g["lng"]:.5f}</span>'
            f'</div>', unsafe_allow_html=True)
        st.markdown("")
        if st.button("🔄 Change Location", use_container_width=True):
            st.session_state.geo_confirmed = False
            st.session_state.geo = None
            st.session_state.candidates = []
            st.rerun()
    else:
        st.caption("Search for your school to pin the exact location. No fallback — you confirm the correct pin.")
        search_input = st.text_input(
            "Search query",
            value=f"{school_name}, {county}, Kenya",
            placeholder="e.g. Machakos High School, Kenya",
            key="geo_search_input"
        )
        search_btn = st.button("🔍 Search Location", type="primary", use_container_width=True)

        if search_btn and search_input.strip():
            with st.spinner("Searching OpenStreetMap..."):
                st.session_state.candidates = search_nominatim(search_input.strip(), limit=5)
                st.session_state.search_query = search_input.strip()

        # Manual coordinate entry
        with st.expander("📌 Enter coordinates manually"):
            man_lat = st.number_input("Latitude",  value=-1.2921, format="%.5f", key="man_lat")
            man_lng = st.number_input("Longitude", value=36.8219, format="%.5f", key="man_lng")
            man_lbl = st.text_input("Label", value=school_name, key="man_lbl")
            if st.button("✅ Use These Coordinates", use_container_width=True):
                st.session_state.geo = {
                    "lat": man_lat, "lng": man_lng,
                    "display_name": f"{man_lbl} (manual entry)",
                    "short_label": man_lbl,
                    "type": "manual",
                }
                st.session_state.geo_confirmed = True
                st.session_state.candidates = []
                st.rerun()


# ─────────────────────────────────────────────────────────────
# CANDIDATE PICKER — shown in main area when not confirmed
# ─────────────────────────────────────────────────────────────
if not st.session_state.geo_confirmed:
    st.markdown('<div class="main-title">🔥 CleanCook</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">School Energy Transition Platform</div>', unsafe_allow_html=True)
    st.markdown("---")

    candidates = st.session_state.candidates

    if not candidates and not st.session_state.search_query:
        # Fresh start — prompt the user
        st.markdown("""
<div class="geo-pending">
<b>📍 Start by locating your school</b><br>
Use the search box in the sidebar to find your school on the map.
You will choose the exact location from search results — no guessing, no fallback.
</div>
""", unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        col_a.markdown("""
**How it works:**
1. Enter your school name and county in the sidebar
2. Click **Search Location**
3. Pick the correct result from the list
4. Or enter exact lat/lng coordinates manually
5. Once confirmed, the full app unlocks
        """)
        col_b.markdown("""
**Tips for better results:**
- Use the official registered school name
- Add the county, e.g. *"St. Mary's Mumias, Kakamega"*
- Try shorter versions if not found, e.g. *"Mumias High School"*
- Check spelling — OpenStreetMap uses official names
- Use manual coordinates as a last resort (from Google Maps)
        """)

    elif not candidates and st.session_state.search_query:
        # Searched but nothing returned
        st.error(
            f"❌ No results found for **\"{st.session_state.search_query}\"** in Kenya on OpenStreetMap.\n\n"
            "**Try:**\n"
            "- A shorter version of the name (e.g. just the distinctive part)\n"
            "- Remove 'Catholic' / 'High School' if it was added automatically\n"
            "- Search just the town/area name to verify it exists in OSM\n"
            "- Use the **manual coordinates** option in the sidebar (paste from Google Maps)"
        )
        st.markdown('<div class="geo-search-hint">💡 <b>Getting coordinates from Google Maps:</b> Right-click any location on Google Maps → the coordinates appear at the top of the context menu. Copy and paste them into the manual entry box.</div>', unsafe_allow_html=True)

    else:
        # Show candidates for user to pick
        st.markdown("### 📍 Select the correct location")
        st.markdown(
            f"Found **{len(candidates)} result(s)** for *\"{st.session_state.search_query}\"*. "
            "Pick the one that matches your school:"
        )

        # Preview map showing all candidates
        center_lat = sum(c["lat"] for c in candidates) / len(candidates)
        center_lng = sum(c["lng"] for c in candidates) / len(candidates)
        preview_map = folium.Map(location=[center_lat, center_lng], zoom_start=8,
                                 tiles="CartoDB positron")
        colors = ["green","blue","orange","red","purple"]
        for i, cand in enumerate(candidates):
            folium.Marker(
                [cand["lat"], cand["lng"]],
                tooltip=f"#{i+1} — {cand['short_label'][:50]}",
                popup=folium.Popup(
                    f"<b>#{i+1}</b><br>{cand['display_name'][:120]}<br>"
                    f"<small>Lat: {cand['lat']:.5f}, Lng: {cand['lng']:.5f}</small>",
                    max_width=250),
                icon=folium.Icon(color=colors[i % len(colors)],
                                 icon="map-marker", prefix="fa"),
            ).add_to(preview_map)

        col_map_prev, col_list = st.columns([2, 1])
        with col_map_prev:
            st_folium(preview_map, width=620, height=380)

        with col_list:
            st.markdown("**Choose your school:**")
            for i, cand in enumerate(candidates):
                type_label = cand.get("type", "place").replace("_", " ").title()
                col_btn, col_info = st.columns([1, 4])
                with col_info:
                    st.markdown(
                        f'<div class="candidate-card">'
                        f'<div class="candidate-type">#{i+1} · {type_label}</div>'
                        f'<div class="candidate-name">{cand["short_label"][:55]}</div>'
                        f'<div class="candidate-addr">{cand["display_name"][: 80]}...</div>'
                        f'<div class="candidate-coord">{cand["lat"]:.5f}, {cand["lng"]:.5f}</div>'
                        f'</div>',
                        unsafe_allow_html=True
                    )
                with col_btn:
                    if st.button(f"✅ #{i+1}", key=f"pick_{i}", use_container_width=True):
                        st.session_state.geo = cand
                        st.session_state.geo_confirmed = True
                        st.session_state.candidates = []
                        st.rerun()

            st.markdown("---")
            st.markdown("**None of these?**")
            st.markdown("Use the **manual coordinates** option in the sidebar.")

    st.stop()   # ← STOP rendering the rest of the app until location is confirmed


# ─────────────────────────────────────────────────────────────
# FROM HERE: location is confirmed — render full app
# ─────────────────────────────────────────────────────────────
geo     = st.session_state.geo
lat     = geo["lat"]
lng     = geo["lng"]
sizing  = calculate_sizing(num_students, meals_per_day)
costs   = calculate_costs(sizing, fuel_type)
alt_fuel  = "Electric" if fuel_type == "LPG" else "LPG"
costs_alt = calculate_costs(sizing, alt_fuel)

# ─────────────────────────────────────────────────────────────
# HEADER + METRICS
# ─────────────────────────────────────────────────────────────
st.markdown('<div class="main-title">🔥 CleanCook</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">School Energy Transition Platform — Size · Cost · Validate</div>',
            unsafe_allow_html=True)
st.markdown("---")

m1, m2, m3, m4, m5 = st.columns(5)
for col, val, lbl in [
    (m1, f"{num_students:,}",                       "Students"),
    (m2, f"{sizing['total_litres']:,}L",             "Litres / Day"),
    (m3, str(sizing['stoves_needed']),                "Stoves Needed"),
    (m4, f"KES {costs['grand']:,.0f}",               f"Est. Cost ({fuel_type})"),
    (m5, f"KES {costs['grand']//num_students:,}",    "Cost / Student"),
]:
    col.markdown(
        f'<div class="metric-card"><div class="metric-val">{val}</div>'
        f'<div class="metric-lbl">{lbl}</div></div>', unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────
tab_map, tab_size, tab_calc, tab_agent, tab_dd = st.tabs([
    "🗺️  School Map",
    "📐  Sizing & Costs",
    "🧮  How Calculations Work",
    "🤖  AI Agent",
    "🔍  Due Diligence",
])


# ══════════════════════════════
# TAB 1 — MAP
# ══════════════════════════════
with tab_map:
    st.markdown('<div class="section-head">School Location & Energy Infrastructure</div>',
                unsafe_allow_html=True)

    st.markdown(
        f'<div class="geo-confirmed">'
        f'📍 <b>Confirmed location:</b> {geo["display_name"][:100]}<br>'
        f'<span style="font-family:monospace;font-size:.82rem">'
        f'Lat: {lat:.5f} | Lng: {lng:.5f}</span>'
        f' &nbsp;·&nbsp; <a href="#" style="color:#1a6b3c">Change in sidebar</a>'
        f'</div>',
        unsafe_allow_html=True)

    col_map, col_leg = st.columns([3, 1])
    with col_map:
        m = folium.Map(location=[lat, lng], zoom_start=15, tiles="CartoDB positron")

        # School pin — confirmed exact location
        folium.Marker(
            [lat, lng],
            popup=folium.Popup(
                f"<b>{school_name}</b><br>{county}<br>"
                f"Students: {num_students:,}<br>Fuel: {fuel_type}<br>"
                f"<small>{geo['display_name'][:80]}</small>",
                max_width=240),
            tooltip=f"📍 {school_name}",
            icon=folium.Icon(color="green", icon="home", prefix="fa"),
        ).add_to(m)

        # Electricity substation ~2km N
        sub = offset_coords(lat, lng, 2.0, 0)
        folium.Marker(sub,
            popup="⚡ Electricity Substation (estimated ~2km)",
            tooltip="Substation",
            icon=folium.Icon(color="blue", icon="bolt", prefix="fa")).add_to(m)

        # Power line N–S corridor
        folium.PolyLine(
            [offset_coords(lat,lng,5,180), [lat,lng], offset_coords(lat,lng,5,0)],
            color="#1a6bcc", weight=3, opacity=0.7,
            tooltip="High-voltage power line (estimated corridor)").add_to(m)

        # LPG depot ~3km E
        lpg_pt = offset_coords(lat, lng, 3.0, 90)
        folium.Marker(lpg_pt,
            popup="🔵 LPG Supplier Depot (estimated ~3km east)",
            tooltip="LPG Depot",
            icon=folium.Icon(color="orange", icon="fire", prefix="fa")).add_to(m)

        # Nearest town ~4km SW
        town = offset_coords(lat, lng, 4.0, 225)
        folium.Marker(town,
            popup="🏘️ Nearest Town / Grid Node (estimated ~4km)",
            tooltip="Town Centre",
            icon=folium.Icon(color="red", icon="building", prefix="fa")).add_to(m)

        # 5km infrastructure zone
        folium.Circle([lat,lng], radius=5000, color="#1a6b3c",
            fill=True, fill_opacity=0.05,
            tooltip="5km infrastructure assessment zone").add_to(m)

        folium.LayerControl().add_to(m)
        st_folium(m, width=740, height=500)

    with col_leg:
        st.markdown("**Legend**")
        st.markdown(
            "🟢 **School** — Confirmed pin  \n"
            "🔵 **Substation** — Grid  \n"
            "🟠 **LPG Depot**  \n"
            "🔴 **Town** — Grid node  \n"
            "🔵 **Line** — Power corridor  \n"
            "⭕ **Circle** — 5km zone"
        )
        st.divider()
        st.markdown("**Location Source**")
        src = geo.get("type","")
        if src == "manual":
            st.markdown("📌 Manually entered coordinates")
        else:
            st.markdown("🌍 OpenStreetMap Nominatim")
            st.markdown(f"`{geo.get('type','place')}`")
        st.divider()
        st.markdown('<div class="warning-box">⚠️ Infrastructure markers are indicative. Run Due Diligence for verified utility data.</div>',
                    unsafe_allow_html=True)


# ══════════════════════════════
# TAB 2 — SIZING & COSTS
# ══════════════════════════════
with tab_size:
    st.markdown('<div class="section-head">Equipment Sizing & Cost Breakdown</div>', unsafe_allow_html=True)

    col_s, col_c = st.columns(2)
    with col_s:
        st.markdown("#### 🍲 Pot Allocation")
        st.caption(f"{num_students} × {meals_per_day} meals × 5L = **{sizing['total_litres']:,}L/day**")
        for sz in sorted(sizing["pot_alloc"].keys(), reverse=True):
            cnt = sizing["pot_alloc"][sz]
            st.markdown(f"**{sz}L — {cnt} pot(s)**")
            st.progress(min(cnt / 8, 1.0))
        st.success(f"**{sizing['total_pots']} pots | {sizing['stoves_needed']} stoves** (incl. 20% buffer)")

    with col_c:
        st.markdown(f"#### 💰 Cost — {fuel_type}")
        for item in costs["items"]:
            c1, c2 = st.columns([3,1])
            c1.markdown(item["item"])
            c2.markdown(f"**KES {item['total']:,}**")
        st.markdown("---")
        st.markdown(f"### TOTAL: **KES {costs['grand']:,}**")
        st.markdown(f"Per student: **KES {costs['grand']//num_students:,}**")
        if budget_kes > 0:
            gap = costs["grand"] - budget_kes
            st.error(f"⚠️ Shortfall: KES {gap:,}") if gap > 0 else st.success(f"✅ Surplus: KES {-gap:,}")

    st.divider()
    st.markdown("#### ⚖️ LPG vs Electric Comparison")
    c1, c2 = st.columns(2)
    c1.metric(fuel_type,  f"KES {costs['grand']:,}",     f"KES {costs['grand']//num_students:,}/student")
    c2.metric(alt_fuel,   f"KES {costs_alt['grand']:,}", f"KES {costs_alt['grand']//num_students:,}/student")
    cheaper = fuel_type if costs["grand"] < costs_alt["grand"] else alt_fuel
    st.info(f"💡 **{cheaper}** is cheaper by **KES {abs(costs['grand']-costs_alt['grand']):,}**.")


# ══════════════════════════════
# TAB 3 — HOW CALCULATIONS WORK
# ══════════════════════════════
with tab_calc:
    st.markdown('<div class="section-head">🧮 How the Calculations Work</div>', unsafe_allow_html=True)
    st.markdown("Every number in CleanCook comes from a documented formula. This tab explains each step.")

    st.markdown("### 📏 Step 1 — Daily Cooking Volume")
    st.markdown('<div class="calc-step"><b>Goal:</b> Determine total litres needed per day.<br><b>Benchmark:</b> Machakos High School (1×1000L + 1×500L + 3×200L pots for ~800 students, 3 meals/day) → 5L per student per meal.</div>', unsafe_allow_html=True)
    st.markdown('<div class="calc-formula">Total Litres/Day  =  Students × Meals/Day × 5L</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="calc-example">📌 Your school: {num_students:,} × {meals_per_day} × 5 = <b>{sizing["total_litres"]:,}L/day</b></div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### 🍲 Step 2 — Pot Size Allocation")
    st.markdown('<div class="calc-step"><b>Goal:</b> Assign 200L → 100L → 50L pots to meet daily volume.<br><b>80% fill rule:</b> Pots must not be brim-filled — liquid expands when cooking. Industry standard is 80% max.</div>', unsafe_allow_html=True)
    st.markdown('<div class="calc-formula">Usable capacity = Pot Size × 0.80\nPots of 200L    = floor(Total Litres ÷ 160)\nRemainder       → repeat for 100L, then 50L</div>', unsafe_allow_html=True)
    alloc_str = " + ".join(f"{c}×{s}L" for s,c in sorted(sizing["pot_alloc"].items(),reverse=True))
    st.markdown(f'<div class="calc-example">📌 Your school: {alloc_str} = <b>{sizing["total_pots"]} pots</b></div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### 🔥 Step 3 — Number of Stoves")
    st.markdown('<div class="calc-step"><b>Goal:</b> Stoves needed including 20% operational spare capacity for breakdowns and maintenance.</div>', unsafe_allow_html=True)
    st.markdown('<div class="calc-formula">Stoves = ceil(Total Pots × 1.20)</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="calc-example">📌 Your school: ceil({sizing["total_pots"]} × 1.20) = <b>{sizing["stoves_needed"]} stoves</b></div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### 💰 Step 4 — Cost Estimation")
    st.markdown('<div class="calc-step"><b>Prices:</b> Kenya market rates 2024–25. Electric costs more due to 3-phase power requirements (KPLC licensed installation).</div>', unsafe_allow_html=True)
    col_t1, col_t2, col_t3 = st.columns(3)
    col_t1.markdown("**LPG Stoves**"); col_t1.table({"Size":["200L","100L","50L"],"KES":["35,000","22,000","14,000"]})
    col_t2.markdown("**Electric**"); col_t2.table({"Size":["200L","100L","50L"],"KES":["55,000","38,000","22,000"]})
    col_t3.markdown("**Pots**"); col_t3.table({"Size":["200L","100L","50L"],"KES":["28,000","16,000","9,000"]})
    st.markdown('<div class="calc-formula">Equipment = Σ(stove × qty) + infrastructure/stove\nPots      = Σ(pot × qty)\nInstall   = (Equipment + Pots) × 15%(LPG) or 20%(Electric)\nTOTAL     = Equipment + Pots + Install</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="calc-example">📌 Your school ({fuel_type}): Equipment KES {costs["equip"]:,} + Pots KES {costs["pot_s"]:,} + Install KES {costs["inst"]:,} = <b>KES {costs["grand"]:,}</b></div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📍 Step 5 — School Geolocation")
    st.markdown('<div class="calc-step"><b>How it works:</b> You searched OpenStreetMap Nominatim and selected a result. No automatic fallback — you confirmed the exact pin.</div>', unsafe_allow_html=True)
    src_type = "Manual coordinates" if geo.get("type")=="manual" else "OpenStreetMap Nominatim"
    st.markdown(f'<div class="calc-example">📌 Source: {src_type}<br>Location: {geo["display_name"][:100]}<br>Coordinates: {lat:.5f}, {lng:.5f}</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📋 Assumptions Summary")
    st.table({
        "Parameter":  ["Litres/student/meal","Pot fill limit","Stove buffer","LPG infra","Electric infra","LPG install","Electric install"],
        "Value":      ["5L","80%","+20%","KES 18k/stove","KES 25k/stove","15%","20%"],
        "Source":     ["Machakos benchmark","Boil-over safety","Operational continuity","Cylinders+regulators","3-phase wiring+panel","Gas fitting","Licensed electrician"],
    })


# ══════════════════════════════
# TAB 4 — AI AGENT
# ══════════════════════════════
with tab_agent:
    st.markdown('<div class="section-head">🤖 CleanCook AI Agent</div>', unsafe_allow_html=True)

    if not openai_key:
        st.warning("⚠️ Enter your OpenAI API key in the sidebar.")
    else:
        @tool
        def size_cooking_equipment_tool(num_students: int, meals_per_day: int = 3) -> str:
            """Calculate recommended pot sizes for a school.
            Args:
                num_students: Total number of students.
                meals_per_day: Meals cooked per day (1, 2, or 3).
            """
            s = calculate_sizing(num_students, meals_per_day)
            lines = [f"Total litres/day: {s['total_litres']:,}", "Pot allocation:"]
            for sz, cnt in sorted(s["pot_alloc"].items(), reverse=True):
                lines.append(f"  {cnt}× {sz}L")
            lines += [f"Total pots: {s['total_pots']}", f"Stoves (+20% buffer): {s['stoves_needed']}"]
            return "\n".join(lines)

        @tool
        def estimate_transition_cost_tool(num_students: int, fuel_type: str, meals_per_day: int = 3) -> str:
            """Estimate KES cost to transition a school from firewood to clean cooking.
            Args:
                num_students: Number of students.
                fuel_type: 'LPG' or 'Electric'.
                meals_per_day: Meals per day (1-3).
            """
            fuel = "LPG" if "lpg" in fuel_type.lower() else "Electric"
            s = calculate_sizing(num_students, meals_per_day)
            c = calculate_costs(s, fuel)
            return (f"Fuel: {fuel}\nEquipment: KES {c['equip']:,}\nPots: KES {c['pot_s']:,}\n"
                    f"Installation: KES {c['inst']:,}\nTOTAL: KES {c['grand']:,} (KES {c['grand']//num_students:,}/student)")

        @tool
        def compare_fuel_options_tool(num_students: int, meals_per_day: int = 3) -> str:
            """Compare LPG vs Electric transition costs side by side.
            Args:
                num_students: Number of students.
                meals_per_day: Meals per day.
            """
            s = calculate_sizing(num_students, meals_per_day)
            lpg  = calculate_costs(s, "LPG")
            elec = calculate_costs(s, "Electric")
            cheaper = "LPG" if lpg["grand"] < elec["grand"] else "Electric"
            return (f"LPG:      KES {lpg['grand']:,} ({lpg['grand']//num_students:,}/student)\n"
                    f"Electric: KES {elec['grand']:,} ({elec['grand']//num_students:,}/student)\n"
                    f"Cheaper: {cheaper} by KES {abs(lpg['grand']-elec['grand']):,}")

        @tool
        def get_benchmark_data_tool() -> str:
            """Return the Machakos High School benchmark used for sizing."""
            return "Machakos High School: 1×1000L + 1×500L + 3×200L pots → 5L/student/meal baseline."

        agent_tools = [size_cooking_equipment_tool, estimate_transition_cost_tool,
                       compare_fuel_options_tool, get_benchmark_data_tool]
        if tavily_key:
            os.environ["TAVILY_API_KEY"] = tavily_key
            agent_tools.append(TavilySearch(max_results=5, topic="general"))

        os.environ["OPENAI_API_KEY"] = openai_key
        llm = ChatOpenAI(model="gpt-4o", temperature=0.1, openai_api_key=openai_key)
        agent = create_agent(llm, agent_tools,
            system_prompt=(
                f"You are CleanCook, helping {school_name} in {county}, Kenya "
                f"transition from firewood to {fuel_type} cooking for {num_students} students "
                f"({meals_per_day} meals/day). All costs in KES. Be concise and practical."
            ), name="cleancook_agent")

        for msg in st.session_state.chat_msgs:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        c1, c2, c3 = st.columns(3)
        for col, sug in zip([c1,c2,c3], [
            f"Size equipment for {num_students} students",
            f"What will {fuel_type} transition cost?",
            "Compare LPG vs Electric"
        ]):
            if col.button(sug):
                st.session_state.pending = sug

        prompt = st.chat_input("Ask CleanCook anything...")
        if not prompt and "pending" in st.session_state:
            prompt = st.session_state.pop("pending")
        if prompt:
            st.session_state.chat_msgs.append({"role":"user","content":prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        result = agent.invoke({"messages":[{"role":"user","content":prompt}]})
                        response = result["messages"][-1].content
                    except Exception as e:
                        response = f"⚠️ Error: {e}"
                st.markdown(response)
                st.session_state.chat_msgs.append({"role":"assistant","content":response})
        if st.button("🗑️ Clear Chat"):
            st.session_state.chat_msgs = []
            st.rerun()


# ══════════════════════════════
# TAB 5 — DUE DILIGENCE
# ══════════════════════════════
with tab_dd:
    st.markdown('<div class="section-head">🔍 Due Diligence Report</div>', unsafe_allow_html=True)
    st.markdown(f"Live Tavily research on **{school_name}**, **{county}**.")

    if not tavily_key:
        st.warning("⚠️ Enter your Tavily API key in the sidebar.")
    elif not openai_key:
        st.warning("⚠️ Enter your OpenAI API key for the AI summary.")
    else:
        if st.button("🚀 Run Full Due Diligence", type="primary"):
            os.environ["TAVILY_API_KEY"] = tavily_key
            os.environ["OPENAI_API_KEY"] = openai_key
            tavily = TavilySearch(max_results=5, topic="general", search_depth="advanced", include_answer=True)
            queries = [
                (f"{school_name} {county} Kenya Catholic school",           "🏫 School Background"),
                (f"electricity grid access {county} Kenya rural schools",   "⚡ Electricity Infrastructure"),
                (f"LPG suppliers distributors {county} Kenya",              "🔵 LPG Availability"),
                (f"clean cooking LPG schools Kenya programme",              "🌍 Clean Cooking Programmes"),
                (f"KPLC Kenya Power grid expansion {county}",              "🔌 Grid Expansion Plans"),
            ]
            dd_data = {}
            prog = st.progress(0)
            for i, (q, section) in enumerate(queries):
                try:
                    raw = tavily.invoke({"query": q})
                    dd_data[section] = json.loads(raw) if isinstance(raw, str) else raw
                except Exception as e:
                    dd_data[section] = {"error": str(e)}
                prog.progress((i+1)/len(queries))

            st.markdown(f"## Report: {school_name} — {county}")
            st.divider()
            for section, data in dd_data.items():
                st.markdown(f"### {section}")
                if "error" in data:
                    st.error(f"Error: {data['error']}"); continue
                if data.get("answer"):
                    st.markdown(f'<div class="dd-card"><b>Summary:</b> {data["answer"]}</div>', unsafe_allow_html=True)
                for r in data.get("results",[])[:3]:
                    snip = r.get("content","")[:300]
                    if snip:
                        st.markdown(
                            f'<div class="dd-card"><b>{r.get("title","")}</b><br>{snip}...'
                            f'<div class="dd-source">🔗 <a href="{r.get("url","")}" target="_blank">{r.get("url","")}</a>'
                            f' | Score: {r.get("score",0):.2f}</div></div>',
                            unsafe_allow_html=True)

            st.divider()
            st.markdown("### 🤖 AI Summary")
            with st.spinner("Generating recommendation..."):
                try:
                    ctx = "\n".join(
                        f"{sec}: " + " | ".join(r.get("content","")[:150] for r in data.get("results",[])[:2])
                        for sec, data in dd_data.items() if "error" not in data)
                    llm_dd = ChatOpenAI(model="gpt-4o", temperature=0.1, openai_api_key=openai_key)
                    summary = llm_dd.invoke(
                        f"Due diligence for {school_name}, {county}, Kenya. "
                        f"{fuel_type} transition for {num_students} students.\n\n{ctx}\n\n"
                        f"Write 6-8 bullet points: school viability, grid access, LPG supply, "
                        f"risks, recommendation (LPG/Electric/hybrid). Kenya context.")
                    st.markdown(summary.content)
                except Exception as e:
                    st.error(f"Error: {e}")


# ─────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#aaa;font-size:.8rem'>"
    "CleanCook v3 · LangChain + Tavily + OpenStreetMap + Streamlit · "
    "Benchmark: Machakos High School, Kenya"
    "</div>", unsafe_allow_html=True)