"""
CleanCook Streamlit App v6
===========================
Geolocation change:
  - NO text search. NO Nominatim. NO OSM dependency.
  - User opens an interactive Kenya map and CLICKS to place their school pin.
  - The click coordinates are captured by streamlit-folium's returned data.
  - Coordinates shown live; user confirms with a button.
  - Works for ANY school in Kenya — regardless of OSM coverage.

All other v5 features retained:
  - Ingredient-level Kenya meal cost engine (KIPPRA 2024 data)
  - Firewood vs clean cooking savings analysis
  - Equipment sizing & amortisation
  - LangChain agent + Tavily due diligence

Requirements:
    pip install streamlit langchain langchain-openai langchain-tavily langgraph folium streamlit-folium requests python-dotenv

Run:
    streamlit run cleancook_app.py
"""

import os, json, math, requests
import streamlit as st
import folium
from folium.plugins import MousePosition
from streamlit_folium import st_folium
from langchain.tools import tool
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

st.set_page_config(page_title="CleanCook — School Energy Transition",
                   page_icon="🔥", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap');
  html,body,[class*="css"]{font-family:'DM Sans',sans-serif;}
  .main-title{font-family:'DM Serif Display',serif;font-size:2.4rem;color:#1a6b3c;line-height:1.2;margin-bottom:0;}
  .subtitle{color:#666;font-size:1rem;margin-top:4px;}
  .metric-card{background:white;border:1px solid #ddd8cc;border-radius:12px;padding:18px 20px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,.04);}
  .metric-val{font-family:'DM Serif Display',serif;font-size:1.8rem;color:#1a6b3c;}
  .metric-val.red{color:#c0392b;} .metric-val.amber{color:#e07b2a;} .metric-val.green{color:#1a6b3c;}
  .metric-lbl{font-size:0.78rem;color:#888;text-transform:uppercase;letter-spacing:.4px;}
  .section-head{font-family:'DM Serif Display',serif;font-size:1.3rem;color:#1c1c1c;border-bottom:2px solid #e8f5ee;padding-bottom:8px;margin-bottom:16px;}
  .saving-banner{background:linear-gradient(135deg,#1a6b3c,#2d9058);color:white;border-radius:14px;padding:24px 32px;text-align:center;margin:16px 0;}
  .saving-banner .big{font-family:'DM Serif Display',serif;font-size:3rem;line-height:1;}
  .saving-banner .lbl{font-size:1rem;opacity:.85;margin-top:4px;}
  .cost-fw{background:#fde8e8;border-left:4px solid #c0392b;border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:6px;font-size:.9rem;}
  .cost-cc{background:#e8f5ee;border-left:4px solid #1a6b3c;border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:6px;font-size:.9rem;}
  .cost-neu{background:#f7f7f4;border-left:4px solid #888;border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:6px;font-size:.9rem;}
  .source-badge{background:#f0f7f3;border:1px solid #b3ddc0;border-radius:6px;padding:4px 10px;font-size:.75rem;color:#1a4a2c;display:inline-block;margin:2px 0;}
  .calc-step{background:#f7f7f4;border-left:4px solid #1a6b3c;border-radius:0 10px 10px 0;padding:14px 18px;margin-bottom:12px;font-size:.93rem;line-height:1.7;}
  .calc-formula{background:#1c1c1c;color:#7ee8a2;border-radius:8px;padding:12px 16px;font-family:monospace;font-size:.9rem;margin:8px 0;white-space:pre;}
  .calc-example{background:#e8f5ee;border-radius:8px;padding:10px 14px;font-size:.88rem;color:#1a4a2c;margin:6px 0;}
  .dd-card{background:#f7f7f4;border-left:4px solid #1a6b3c;border-radius:0 10px 10px 0;padding:14px 18px;margin-bottom:10px;font-size:.93rem;line-height:1.6;}
  .dd-source{font-size:.75rem;color:#888;margin-top:4px;}
  .warning-box{background:#fdf3e7;border-left:4px solid #e07b2a;border-radius:0 10px 10px 0;padding:12px 16px;font-size:.88rem;color:#7a4a1a;}
  .geo-confirmed{background:#e8f5ee;border:2px solid #1a6b3c;border-radius:10px;padding:12px 16px;font-size:.9rem;color:#1a4a2c;margin-bottom:12px;}
  .pin-hint{background:#f0f7ff;border:2px dashed #4a90d9;border-radius:10px;padding:20px 24px;text-align:center;font-size:1rem;color:#1a3a6b;margin-bottom:16px;}
  .pin-pending{background:#fdf3e7;border:2px solid #e07b2a;border-radius:10px;padding:12px 16px;font-size:.9rem;color:#7a4a1a;margin-bottom:12px;}
  .stButton>button{background:#1a6b3c !important;color:white !important;border-radius:8px !important;font-weight:600 !important;border:none !important;padding:10px 24px !important;}
  .stButton>button:hover{background:#2d9058 !important;}
</style>
""", unsafe_allow_html=True)


# ─── HELPERS ──────────────────────────────────────────────────
def offset_coords(lat, lng, d, b):
    R=6371; b=math.radians(b); lr=math.radians(lat)
    lat2=math.asin(math.sin(lr)*math.cos(d/R)+math.cos(lr)*math.sin(d/R)*math.cos(b))
    lng2=math.radians(lng)+math.atan2(math.sin(b)*math.sin(d/R)*math.cos(lr),
                                       math.cos(d/R)-math.sin(lr)*math.sin(lat2))
    return math.degrees(lat2), math.degrees(lng2)


# ─── COMMODITY PRICES (Kenya 2025) ────────────────────────────
COMMODITY_DEFAULTS = {
    "maize_flour_kg":    {"default":58,  "unit":"KES/kg","label":"Maize flour",       "desc":"~KES 5,200/90kg bag"},
    "beans_kg":          {"default":90,  "unit":"KES/kg","label":"Dry beans",         "desc":"~KES 8,100/90kg bag"},
    "rice_kg":           {"default":120, "unit":"KES/kg","label":"Rice",              "desc":"Pishori/broken rice"},
    "sorghum_millet_kg": {"default":50,  "unit":"KES/kg","label":"Sorghum/millet",    "desc":"For uji porridge"},
    "omena_kg":          {"default":200, "unit":"KES/kg","label":"Omena (dried fish)","desc":"Budget protein"},
    "meat_kg":           {"default":650, "unit":"KES/kg","label":"Beef/goat meat",    "desc":"Bulk buying price"},
    "sukuma_wiki_kg":    {"default":25,  "unit":"KES/kg","label":"Sukuma wiki",       "desc":"Most common school veg"},
    "tomatoes_kg":       {"default":60,  "unit":"KES/kg","label":"Tomatoes",          "desc":"For stew base"},
    "cooking_oil_L":     {"default":230, "unit":"KES/L", "label":"Cooking oil",       "desc":"20L jerrican ÷ 20"},
    "salt_kg":           {"default":20,  "unit":"KES/kg","label":"Salt",              "desc":"Bulk institutional"},
    "milk_L":            {"default":65,  "unit":"KES/L", "label":"Milk",              "desc":"Bulk/UHT for tea"},
    "tea_leaves_kg":     {"default":400, "unit":"KES/kg","label":"Tea leaves",        "desc":"Kericho loose leaf"},
    "sugar_kg":          {"default":160, "unit":"KES/kg","label":"Sugar",             "desc":"Retail white sugar"},
    "labour_overhead_pct":{"default":20, "unit":"%",     "label":"Labour & overhead", "desc":"% of food cost"},
}

MEAL_RECIPES = {
    "breakfast":{
        "label":"🌅 Breakfast","desc":"Uji porridge + milk tea",
        "ingredients":[
            {"commodity":"sorghum_millet_kg","grams":30,"notes":"Uji flour"},
            {"commodity":"maize_flour_kg",   "grams":20,"notes":"Maize blend"},
            {"commodity":"sugar_kg",         "grams":15,"notes":"Porridge sugar"},
            {"commodity":"milk_L",           "grams":50,"notes":"Porridge milk"},
            {"commodity":"tea_leaves_kg",    "grams":2, "notes":"Tea leaves"},
            {"commodity":"milk_L",           "grams":60,"notes":"Tea milk"},
            {"commodity":"sugar_kg",         "grams":10,"notes":"Tea sugar"},
        ],
        "firewood_fuel_share":0.10,
    },
    "lunch":{
        "label":"☀️ Lunch","desc":"Ugali + githeri + sukuma wiki",
        "ingredients":[
            {"commodity":"maize_flour_kg","grams":300,"notes":"Ugali flour"},
            {"commodity":"beans_kg",      "grams":80, "notes":"Githeri beans"},
            {"commodity":"maize_flour_kg","grams":30, "notes":"Githeri maize"},
            {"commodity":"sukuma_wiki_kg","grams":80, "notes":"Kale side"},
            {"commodity":"tomatoes_kg",   "grams":30, "notes":"Sukuma base"},
            {"commodity":"cooking_oil_L", "grams":8,  "notes":"Cooking oil"},
            {"commodity":"salt_kg",       "grams":3,  "notes":"Salt"},
        ],
        "firewood_fuel_share":0.22,
    },
    "supper":{
        "label":"🌙 Supper","desc":"Rice/ugali + omena/beans stew + vegetables",
        "ingredients":[
            {"commodity":"rice_kg",       "grams":150,"notes":"Rice (dry)"},
            {"commodity":"maize_flour_kg","grams":100,"notes":"Ugali (alt days)"},
            {"commodity":"omena_kg",      "grams":30, "notes":"Omena stew"},
            {"commodity":"beans_kg",      "grams":50, "notes":"Beans stew"},
            {"commodity":"sukuma_wiki_kg","grams":60, "notes":"Cooked greens"},
            {"commodity":"tomatoes_kg",   "grams":40, "notes":"Stew base"},
            {"commodity":"cooking_oil_L", "grams":12, "notes":"Cooking oil"},
            {"commodity":"salt_kg",       "grams":3,  "notes":"Salt"},
        ],
        "firewood_fuel_share":0.20,
    },
}

WEEKS_PER_TERM=13; DAYS_PER_WEEK=7; TERMS_PER_YEAR=3
EQUIPMENT_LIFE=7; CLEAN_FUEL_SAVE=0.40


def compute_meal_cost(meal_key, prices):
    recipe=MEAL_RECIPES[meal_key]; labour_pct=prices["labour_overhead_pct"]/100
    ingredients=[]; food_cost=0.0
    for ing in recipe["ingredients"]:
        com=ing["commodity"]; p=prices[com]; cost=(ing["grams"]/1000)*p
        food_cost+=cost
        ingredients.append({"name":COMMODITY_DEFAULTS[com]["label"],
            "qty":f"{ing['grams']}{'ml' if '_L' in com else 'g'}",
            "price":f"KES {p}/{COMMODITY_DEFAULTS[com]['unit'].split('/')[1]}",
            "cost":cost,"notes":ing["notes"]})
    labour_cost=food_cost*labour_pct; fuel_cost=food_cost*recipe["firewood_fuel_share"]
    total_cost=food_cost+labour_cost+fuel_cost
    return {"key":meal_key,"label":recipe["label"],"desc":recipe["desc"],
            "ingredients":ingredients,"food_cost":food_cost,"fuel_cost":fuel_cost,
            "labour_cost":labour_cost,"total_cost":total_cost,"fuel_share":recipe["firewood_fuel_share"]}

def compute_all_meals(served_meals, prices):
    meals={}; daily=0.0
    for k in served_meals:
        m=compute_meal_cost(k,prices); meals[k]=m; daily+=m["total_cost"]
    w=daily*DAYS_PER_WEEK; t=w*WEEKS_PER_TERM
    return {"meals":meals,"daily":daily,"weekly":w,"term":t,"annual":t*TERMS_PER_YEAR}

def compute_clean_cook(fw):
    cc_meals={}; daily=0.0
    for k,m in fw["meals"].items():
        nf=m["fuel_cost"]*(1-CLEAN_FUEL_SAVE); nt=m["food_cost"]+m["labour_cost"]+nf
        cc_meals[k]={**m,"cc_fuel_cost":nf,"cc_total_cost":nt,"saving_per_day":m["total_cost"]-nt}
        daily+=nt
    w=daily*DAYS_PER_WEEK; t=w*WEEKS_PER_TERM
    return {"meals":cc_meals,"daily":daily,"weekly":w,"term":t,"annual":t*TERMS_PER_YEAR,
            "saving_daily":fw["daily"]-daily,"saving_weekly":fw["weekly"]-w,"saving_term":fw["term"]-t}

STOVE_COSTS={"LPG":{200:35_000,100:22_000,50:14_000},"Electric":{200:55_000,100:38_000,50:22_000}}
POT_COSTS={200:28_000,100:16_000,50:9_000}
INFRA_COSTS={"LPG":18_000,"Electric":25_000}
INSTALL_RATE={"LPG":0.15,"Electric":0.20}

def calc_sizing(n,m):
    total=n*m*5; alloc={}; rem=total
    for sz in [200,100,50]:
        cnt=int(rem//(sz*0.8))
        if cnt>0: alloc[sz]=cnt; rem-=cnt*sz*0.8
    if rem>0: alloc[50]=alloc.get(50,0)+1
    tp=sum(alloc.values())
    return {"total_litres":total,"pot_alloc":alloc,"total_pots":tp,"stoves":math.ceil(tp*1.2)}

def calc_equip(sizing,fuel):
    alloc=sizing["pot_alloc"]; stoves=sizing["stoves"]; sc=STOVE_COSTS[fuel]
    sv=sum(sc[s]*c for s,c in alloc.items()); pv=sum(POT_COSTS[s]*c for s,c in alloc.items())
    iv=INFRA_COSTS[fuel]*stoves; eq=sv+iv; inst=int((eq+pv)*INSTALL_RATE[fuel])
    items=[]
    for s,c in sorted(alloc.items(),reverse=True):
        items.append({"item":f"{c}× {'LPG burner' if fuel=='LPG' else 'Induction'} ({s}L)","total":sc[s]*c})
    for s,c in sorted(alloc.items(),reverse=True):
        items.append({"item":f"{c}× Pot ({s}L)","total":POT_COSTS[s]*c})
    items.append({"item":"Infrastructure","total":iv})
    items.append({"item":f"Install ({int(INSTALL_RATE[fuel]*100)}%)","total":inst})
    return {"stove":sv,"pot":pv,"infra":iv,"equip":eq,"inst":inst,"grand":eq+pv+inst,"items":items}

def calc_fw(n,fw_price,fw_kg):
    d=fw_price*fw_kg; w=d*7; t=w*13; a=t*3
    return {"daily":d,"weekly":w,"term":t,"annual":a,
            "per_student_day":d/n if n else 0,"per_student_week":w/7/n if n else 0}


# ─── SESSION STATE ─────────────────────────────────────────────
for k,v in [("geo_confirmed",False),("geo",None),("clicked_lat",None),
             ("clicked_lng",None),("chat_msgs",[]),("geo_status",""),
             ("geo_source",""),("selected_institution",None)]:
    if k not in st.session_state: st.session_state[k]=v


# ─── INSTITUTION DATABASE (loaded from CSV upload) ──────────────
import csv as _csv, re as _re, io as _io

def _parse_gps(gps_str):
    if not gps_str or not gps_str.strip(): return None, None
    gps = gps_str.strip()
    m = _re.match(r"^(-?\d+\.\d+)\s+(-?\d+\.\d+)", gps)
    if m: return float(m.group(1)), float(m.group(2))
    clean = gps.replace('""'  , '"'  )
    lat_m = _re.search(r"(-?\d+)[°º](\d+)[\'′](\d+\.?\d*)[\"\u2033]{1,2}\s*([NSns])", clean)
    lon_m = _re.search(r"(\d+)[°º](\d+)[\'′](\d+\.?\d*)[\"\u2033]{1,2}\s*([EWew])", clean)
    if lat_m and lon_m:
        def d(a,b,c,h): v=abs(float(a))+float(b)/60+float(c)/3600; return -v if h.upper() in('S','W') else v
        return d(*lat_m.groups()), d(*lon_m.groups())
    m3 = _re.findall(r"(-?\d+\.?\d*)\s*°?\s*([NSns])[,;\s]+(-?\d+\.?\d*)\s*°?\s*([EWew])", clean)
    if m3: return float(m3[0][0])*(-1 if m3[0][1].upper()=="S" else 1), float(m3[0][2])*(-1 if m3[0][3].upper()=="W" else 1)
    return None, None

def parse_institutions_csv(file_bytes):
    """Parse institutions CSV bytes. Returns sorted list of institution dicts."""
    out = []
    try:
        text = file_bytes.decode("utf-8-sig")
        for r in _csv.DictReader(_io.StringIO(text)):
            lat, lng = _parse_gps(r.get("GPS Location",""))
            name = r.get("Institution Name","").strip()
            if lat and name and -5.0<=lat<=5.0 and 33.9<=lng<=42.0:
                out.append({
                    "name":           name,
                    "lat":            round(lat, 6),
                    "lng":            round(lng, 6),
                    "county":         r.get("County","").strip(),
                    "type":           r.get("Institution Type","").strip(),
                    "ownership":      r.get("Ownership Type","").strip(),
                    "school_type":    r.get("School Type","").strip(),
                    "students":       r.get("Total People","").strip(),
                    "meals_per_day":  r.get("Total Meals Per Day","").strip(),
                    "cooking_method": r.get("Cooking Method","").strip(),
                })
    except Exception:
        pass
    return sorted(out, key=lambda x: x["name"])

# Refreshed each rerun after sidebar uploader populates session state
# (defined again before location picker below)
INSTITUTIONS  = []
INST_NAMES    = []
INST_LOOKUP   = {}

# ─── NOMINATIM (fallback if institution not in database) ─────────
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOM_HEADERS   = {"User-Agent": "CleanCookApp/7.0 (school-energy-transition-kenya)"}

@st.cache_data(show_spinner=False, ttl=3600)
def nominatim_geocode(query: str):
    try:
        r = requests.get(NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "ke"},
            headers=NOM_HEADERS, timeout=10)
        r.raise_for_status()
        results = r.json()
        if results:
            best = results[0]
            return float(best["lat"]), float(best["lon"]), best.get("display_name", query)
    except Exception:
        pass
    return None


# ─── SIDEBAR ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ API Keys")
    openai_key=st.text_input("OpenAI API Key",type="password",value=os.environ.get("OPENAI_API_KEY",""))
    tavily_key=st.text_input("Tavily API Key", type="password",value=os.environ.get("TAVILY_API_KEY",""))
    st.divider()

    st.markdown("### 📂 Institution Database")
    uploaded_csv = st.file_uploader(
        "Upload institutions CSV",
        type=["csv"],
        help="Upload the institutions export CSV file to enable the school search dropdown.",
        label_visibility="collapsed",
    )
    if uploaded_csv is not None:
        raw = uploaded_csv.read()
        parsed = parse_institutions_csv(raw)
        if parsed:
            st.session_state["institutions"] = parsed
            st.caption(f"✅ {len(parsed):,} institutions loaded")
        else:
            st.warning("Could not parse the CSV. Check the file format.")
    elif st.session_state.get("institutions"):
        st.caption(f"✅ {len(st.session_state['institutions']):,} institutions loaded")
    else:
        st.caption("No file loaded — upload to enable institution search.")
    st.divider()

    st.markdown("### 🏫 School Details")
    school_name  =st.text_input("School Name","Gitwe High School")
    county       =st.text_input("County / Region","Kiambu County")
    num_students =st.number_input("Number of Students",10,10000,500,10)
    school_type  =st.selectbox("School Type",["Boarding","Day School","Day & Boarding"])
    fuel_type    =st.radio("Target Fuel Type",["LPG","Electric"],horizontal=True)
    budget_kes   =st.number_input("Available Budget (KES)",0,50_000_000,0,10000)
    st.divider()

    st.markdown("### 🔥 Current Cooking Method")
    current_fuel=st.selectbox("Current method",["Firewood","Charcoal","Kerosene","LPG (partial)","Mixed"])
    fw_price_kg =st.number_input("Firewood price (KES/kg)",1,200,5,1)
    fw_kg_day   =st.number_input("Firewood used per day (kg)",10,5000,200,10)
    st.divider()

    st.markdown("### 🍽️ Meals Served")
    serve_bfast =st.checkbox("Breakfast",value=True)
    serve_lunch =st.checkbox("Lunch",    value=True)
    serve_supper=st.checkbox("Supper",   value=True)
    served_meals=[k for k,v in [("breakfast",serve_bfast),("lunch",serve_lunch),("supper",serve_supper)] if v]
    st.divider()

    st.markdown("### 🛒 Commodity Prices")
    st.caption("Pre-filled with Kenya 2025 market rates. Adjust for your region.")
    prices={}
    with st.expander("📦 Adjust prices for your area",expanded=False):
        for key,meta in COMMODITY_DEFAULTS.items():
            if meta["unit"]=="%":
                prices[key]=st.slider(f"{meta['label']} ({meta['unit']})",5,40,meta["default"],1,
                                      help=meta["desc"],key=f"price_{key}")
            else:
                prices[key]=st.number_input(f"{meta['label']} ({meta['unit']})",1,2000,meta["default"],1,
                                            help=meta["desc"],key=f"price_{key}")
    for key,meta in COMMODITY_DEFAULTS.items():
        if key not in prices: prices[key]=meta["default"]
    st.divider()

    # ── Location status in sidebar ──
    st.markdown("### 📍 School Location")
    if st.session_state.geo_confirmed and st.session_state.geo:
        g    = st.session_state.geo
        inst = g.get("institution")
        src  = g.get("type","")
        src_icon = "🟢" if src=="database" else "📌"
        src_lbl  = "Database" if src=="database" else "Map pin"
        st.markdown(
            f'<div style="background:#e8f5ee;border:2px solid #1a6b3c;border-radius:8px;'
            f'padding:10px 12px;font-size:.83rem;color:#1a4a2c">'
            f'✅ <b>Confirmed</b> · {src_icon} {src_lbl}<br>'
            f'<b style="font-size:.9rem">{g.get("display_name","")[:50]}</b><br>'
            f'<span style="font-family:monospace;font-size:.76rem">{g["lat"]:.5f}, {g["lng"]:.5f}</span>'
            f'</div>', unsafe_allow_html=True)
        if inst:
            st.caption(f"👥 {inst['students']} students · 🍽 {inst['meals_per_day']} meals/day · 🔥 {inst['cooking_method'] or 'Unknown'}")
        st.markdown("")
        if st.button("🔄 Change Location", use_container_width=True):
            st.session_state.geo_confirmed     = False
            st.session_state.geo               = None
            st.session_state.clicked_lat       = None
            st.session_state.clicked_lng       = None
            st.session_state.geo_status        = ""
            st.session_state.geo_source        = ""
            st.session_state.selected_institution = None
            st.rerun()
    else:
        st.caption(f"Search from {len(INSTITUTIONS):,} institutions or click the map.")


# Refresh institution lists from session state each rerun
INSTITUTIONS  = st.session_state.get("institutions", [])
INST_NAMES    = [i["name"] for i in INSTITUTIONS]
INST_LOOKUP   = {i["name"]: i for i in INSTITUTIONS}

# ─── LOCATION PICKER — blocks app until location confirmed ─────
if not st.session_state.geo_confirmed:

    st.markdown('<div class="main-title">🔥 CleanCook</div>',unsafe_allow_html=True)
    st.markdown('<div class="subtitle">School Energy Transition Platform</div>',unsafe_allow_html=True)
    st.markdown("---")

    st.markdown("### 📍 Locate Your School or Institution")
    st.markdown(
        f'<div class="pin-hint">'
        f'Select your institution from the dropdown below ({len(INSTITUTIONS):,} institutions loaded). '
        f'The map will zoom to its exact location. You can also click the map to fine-tune the pin.'
        f'</div>', unsafe_allow_html=True)

    # ── Row 1: Searchable institution dropdown + confirm button ──
    col_drop, col_confirm = st.columns([5, 1])

    with col_drop:
        # st.selectbox has native search/filter built in — type to filter
        inst_options = ["— Type to search or scroll —"] + INST_NAMES
        sel = st.selectbox(
            f"Search institution ({len(INSTITUTIONS):,} available)",
            options=inst_options,
            index=0,
            key="inst_dropdown",
            label_visibility="collapsed",
        )

    with col_confirm:
        select_btn = st.button("📍 Load", type="primary", use_container_width=True,
                               disabled=(sel == "— Type to search or scroll —"))

    # When user selects from dropdown and clicks Load
    if select_btn and sel != "— Type to search or scroll —":
        inst = INST_LOOKUP.get(sel)
        if inst:
            st.session_state.clicked_lat       = inst["lat"]
            st.session_state.clicked_lng       = inst["lng"]
            st.session_state.geo_source        = "database"
            st.session_state.geo_status        = f"✅ {inst['name']} — {inst['county']} ({inst['type']})"
            st.session_state.selected_institution = inst
            st.rerun()

    # ── Row 2: Status message ─────────────────────────────────────
    if st.session_state.geo_status:
        if st.session_state.geo_status.startswith("✅"):
            # Show institution details card
            inst = st.session_state.selected_institution
            if inst:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("County", inst["county"] or "—")
                c2.metric("Students", inst["students"] or "—")
                c3.metric("Meals/Day", inst["meals_per_day"] or "—")
                c4.metric("Current Fuel", inst["cooking_method"] or "—")
        else:
            st.warning(st.session_state.geo_status)

    st.markdown("---")

    # ── Map: show institution pin or let user click ───────────────
    if st.session_state.clicked_lat:
        picker_center = [st.session_state.clicked_lat, st.session_state.clicked_lng]
        picker_zoom   = 15
    else:
        picker_center = [0.0236, 37.9062]
        picker_zoom   = 6

    picker_map = folium.Map(location=picker_center, zoom_start=picker_zoom,
                            tiles="CartoDB positron")

    # Draw pin
    if st.session_state.clicked_lat:
        src = st.session_state.geo_source
        pin_color = "green" if src == "database" else "orange"
        src_label = "From database" if src == "database" else "Map click"
        inst = st.session_state.selected_institution
        popup_html = (
            f"<b>{inst['name'] if inst else school_name}</b><br>"
            f"{inst['county'] if inst else county}<br>"
            f"<small>{src_label}</small><br>"
            f"Students: {inst['students'] if inst else '—'}<br>"
            f"Fuel: {inst['cooking_method'] if inst else '—'}<br>"
            f"Lat: {st.session_state.clicked_lat:.5f}<br>"
            f"Lng: {st.session_state.clicked_lng:.5f}"
        )
        folium.Marker(
            [st.session_state.clicked_lat, st.session_state.clicked_lng],
            tooltip=f"📍 {inst['name'] if inst else school_name} ({src_label})",
            popup=folium.Popup(popup_html, max_width=230),
            icon=folium.Icon(color=pin_color, icon="map-marker", prefix="fa"),
        ).add_to(picker_map)

    # Show all institution markers lightly when zoomed out
    if picker_zoom <= 8:
        for inst_item in INSTITUTIONS[:200]:   # limit for performance
            folium.CircleMarker(
                [inst_item["lat"], inst_item["lng"]],
                radius=3, color="#1a6b3c", fill=True, fill_opacity=0.5,
                tooltip=inst_item["name"],
            ).add_to(picker_map)

    MousePosition(
        position="bottomleft", separator=" | ", prefix="Cursor:",
        lat_formatter="function(num){return num.toFixed(5);}",
        lng_formatter="function(num){return num.toFixed(5);}",
    ).add_to(picker_map)

    col_map, col_side = st.columns([3, 1])
    with col_map:
        map_data = st_folium(picker_map, width=760, height=500,
                             returned_objects=["last_clicked"],
                             key="location_picker")
    with col_side:
        st.markdown("#### How to use")
        st.markdown(
            "**Step 1 — Search dropdown:**\n"
            "- Type school name to filter\n"
            "- Select correct institution\n"
            "- Click **📍 Load** — pin drops\n\n"
            "**Step 2 — Fine-tune (optional):**\n"
            "- Click map to move pin\n"
            "- Zoom in for precision\n\n"
            "**Step 3 — Confirm:**\n"
            "- Click **✅ Confirm** below"
        )
        st.markdown("---")

        if st.session_state.clicked_lat:
            src = st.session_state.geo_source
            src_icon = "🟢" if src=="database" else "📌"
            src_txt  = "Database" if src=="database" else "Map click"
            st.markdown(
                f'<div class="pin-pending">'
                f'<b>{src_icon} {src_txt}</b><br>'
                f'Lat: <code>{st.session_state.clicked_lat:.5f}</code><br>'
                f'Lng: <code>{st.session_state.clicked_lng:.5f}</code>'
                f'</div>', unsafe_allow_html=True)
            st.markdown("")

            if st.button("✅ Confirm Location", type="primary", use_container_width=True):
                inst = st.session_state.selected_institution
                display = (
                    f"{inst['name']}, {inst['county']}" if inst
                    else f"{school_name}, {county} (map pin)"
                )
                st.session_state.geo = {
                    "lat":          st.session_state.clicked_lat,
                    "lng":          st.session_state.clicked_lng,
                    "display_name": display,
                    "type":         st.session_state.geo_source or "map_pin",
                    "institution":  inst,
                }
                st.session_state.geo_confirmed = True
                st.rerun()

            if st.button("🗑️ Clear Pin", use_container_width=True):
                st.session_state.clicked_lat        = None
                st.session_state.clicked_lng        = None
                st.session_state.geo_status         = ""
                st.session_state.geo_source         = ""
                st.session_state.selected_institution = None
                st.rerun()
        else:
            st.info("Search and select an institution, or click the map.")

    # Capture manual map click — overrides database pin
    if map_data and map_data.get("last_clicked"):
        new_lat = map_data["last_clicked"]["lat"]
        new_lng = map_data["last_clicked"]["lng"]
        if new_lat != st.session_state.clicked_lat or new_lng != st.session_state.clicked_lng:
            st.session_state.clicked_lat        = new_lat
            st.session_state.clicked_lng        = new_lng
            st.session_state.geo_source         = "map_pin"
            st.session_state.geo_status         = ""
            st.session_state.selected_institution = None
            st.rerun()

    st.stop()


# ─── CONFIRMED — compute everything ───────────────────────────
geo = st.session_state.get("geo")
if not isinstance(geo, dict) or "lat" not in geo or "lng" not in geo:
    st.session_state.geo_confirmed = False
    st.warning("Location is not confirmed yet. Please select or pin a school location and confirm it.")
    st.stop()

lat, lng = geo["lat"], geo["lng"]
fw_result =compute_all_meals(served_meals,prices)
cc_result =compute_clean_cook(fw_result)
sizing    =calc_sizing(num_students,max(len(served_meals),1))
equip     =calc_equip(sizing,fuel_type)
fw_costs  =calc_fw(num_students,fw_price_kg,fw_kg_day)
amort_term   =equip["grand"]/(EQUIPMENT_LIFE*TERMS_PER_YEAR)
amort_stu_t  =amort_term/num_students if num_students else 0
fw_total_term=fw_result["term"]
cc_total_term=cc_result["term"]+amort_stu_t
saving_term  =fw_total_term-cc_total_term
school_sv_t  =saving_term*num_students
school_sv_yr =school_sv_t*TERMS_PER_YEAR


# ─── HEADER + METRICS ─────────────────────────────────────────
st.markdown('<div class="main-title">🔥 CleanCook</div>',unsafe_allow_html=True)
st.markdown('<div class="subtitle">School Energy Transition Platform — Cost · Compare · Save</div>',unsafe_allow_html=True)
st.markdown("---")
m1,m2,m3,m4,m5=st.columns(5)
for col,val,lbl,cls in [
    (m1,f"{num_students:,}","Students",""),
    (m2,f"KES {fw_result['term']:,.0f}","Meal Cost/Term (FW)","red"),
    (m3,f"KES {fw_result['daily']:,.1f}","Daily Meal/Student","amber"),
    (m4,f"KES {cc_result['daily']:,.1f}",f"Daily Meal ({fuel_type})","green"),
    (m5,f"KES {max(saving_term,0):,.0f}","Saving/Student/Term","green"),
]:
    col.markdown(f'<div class="metric-card"><div class="metric-val {cls}">{val}</div>'
                 f'<div class="metric-lbl">{lbl}</div></div>',unsafe_allow_html=True)
st.markdown("<br>",unsafe_allow_html=True)


# ─── TABS ─────────────────────────────────────────────────────
tab_savings,tab_meals,tab_fw,tab_map_t,tab_equip,tab_calc,tab_agent,tab_dd=st.tabs([
    "💰  Savings Analysis","🍽️  Meal Breakdown","🪵  Firewood Costs",
    "🗺️  School Map","📐  Equipment","🧮  Methodology","🤖  AI Agent","🔍  Due Diligence",
])

# ══ TAB 1 — SAVINGS ══════════════════════════════════════════
with tab_savings:
    st.markdown('<div class="section-head">💰 Firewood vs Clean Cooking — Full Comparison</div>',unsafe_allow_html=True)
    if saving_term>0:
        st.markdown(f'<div class="saving-banner"><div class="lbl">Saving per student per term</div>'
                    f'<div class="big">KES {saving_term:,.0f}</div>'
                    f'<div class="lbl" style="margin-top:8px">Whole school: <b>KES {school_sv_t:,.0f}/term</b> · <b>KES {school_sv_yr:,.0f}/year</b></div>'
                    f'</div>',unsafe_allow_html=True)
    else:
        st.warning("Adjust commodity prices or firewood usage to see projected savings.")
    c1,c2,c3=st.columns(3)
    with c1:
        st.markdown("**🪵 Firewood (Current)**")
        for lbl,val in [("Daily meal cost",f"KES {fw_result['daily']:.1f}"),
                        ("Weekly meal cost",f"KES {fw_result['weekly']:.0f}"),
                        ("Per term",f"KES {fw_result['term']:.0f}"),
                        ("Annual",f"KES {fw_result['annual']:.0f}")]:
            st.markdown(f'<div class="cost-fw"><b>{val}</b><br><span style="font-size:.8rem;color:#7a1a1a">{lbl}</span></div>',unsafe_allow_html=True)
    with c2:
        st.markdown(f"**🔵 {fuel_type} (Proposed)**")
        for lbl,val in [("Daily meal cost",f"KES {cc_result['daily']:.1f}"),
                        ("Weekly meal cost",f"KES {cc_result['weekly']:.0f}"),
                        ("Per term (meals)",f"KES {cc_result['term']:.0f}"),
                        ("+ Equipment amort",f"KES {amort_stu_t:.0f}"),
                        ("Total/term",f"KES {cc_total_term:.0f}")]:
            st.markdown(f'<div class="cost-cc"><b>{val}</b><br><span style="font-size:.8rem;color:#1a4a2c">{lbl}</span></div>',unsafe_allow_html=True)
    with c3:
        st.markdown("**✅ Savings**")
        sv_cls="cost-cc" if saving_term>0 else "cost-neu"
        for lbl,val in [("Saving/week/student",f"KES {cc_result['saving_weekly']:.0f}"),
                        ("Saving/term/student",f"KES {saving_term:.0f}"),
                        ("Saving/year/student",f"KES {saving_term*3:.0f}"),
                        ("Whole school/term",f"KES {school_sv_t:,.0f}"),
                        ("Whole school/year",f"KES {school_sv_yr:,.0f}")]:
            st.markdown(f'<div class="{sv_cls}"><b>{val}</b><br><span style="font-size:.8rem">{lbl}</span></div>',unsafe_allow_html=True)
    st.divider()
    st.markdown("#### ⏱️ Payback & ROI")
    p1,p2,p3=st.columns(3)
    p1.metric("Equipment Investment",f"KES {equip['grand']:,}")
    payback=equip["grand"]/school_sv_yr if school_sv_yr>0 else 0
    p2.metric("Payback Period",f"{payback:.1f} years" if payback>0 else "N/A")
    p3.metric("Equipment Life",f"{EQUIPMENT_LIFE} years")
    if school_sv_yr>0:
        lifetime=school_sv_yr*EQUIPMENT_LIFE-equip["grand"]
        st.success(f"✅ Over {EQUIPMENT_LIFE} years: saves **KES {school_sv_yr*EQUIPMENT_LIFE:,.0f}** against **KES {equip['grand']:,}** investment — net gain **KES {max(lifetime,0):,.0f}**")
    st.divider()
    st.markdown("#### 📅 Weekly Cost Per Student — Meal by Meal")
    hcols=st.columns(5)
    for c,h in zip(hcols,["Meal","🪵 FW/week","🔵 CC/week","💚 Saving/wk","📅 Saving/term"]):
        c.markdown(f"**{h}**")
    for k,m in cc_result["meals"].items():
        fw_w=m["total_cost"]*DAYS_PER_WEEK; cc_w=m["cc_total_cost"]*DAYS_PER_WEEK
        sv_w=m["saving_per_day"]*DAYS_PER_WEEK; sv_t=sv_w*WEEKS_PER_TERM
        row=st.columns(5)
        row[0].markdown(m["label"])
        row[1].markdown(f'<span style="color:#c0392b;font-weight:600">KES {fw_w:.0f}</span>',unsafe_allow_html=True)
        row[2].markdown(f'<span style="color:#1a6b3c;font-weight:600">KES {cc_w:.0f}</span>',unsafe_allow_html=True)
        row[3].markdown(f'<span style="color:#1a6b3c;font-weight:600">KES {sv_w:.0f}</span>',unsafe_allow_html=True)
        row[4].markdown(f'<span style="color:#1a6b3c;font-weight:600">KES {sv_t:.0f}</span>',unsafe_allow_html=True)

# ══ TAB 2 — MEAL BREAKDOWN ════════════════════════════════════
with tab_meals:
    st.markdown('<div class="section-head">🍽️ Meal Cost Breakdown — Kenya Ingredient Pricing</div>',unsafe_allow_html=True)
    st.markdown("Costs estimated from commodity prices, not fixed assumptions. Each meal uses actual recipe gram quantities × current Kenya market rates.")
    st.markdown('<div class="source-badge">📊 KIPPRA 2024: avg secondary meal = KES 38.93/day</div> '
                '<div class="source-badge">🌾 FEWS NET 2024: maize ~KES 58/kg · beans ~KES 90/kg</div>',unsafe_allow_html=True)
    st.markdown("")
    if not served_meals:
        st.warning("No meals selected. Enable meals in sidebar.")
    else:
        for k in served_meals:
            fw_m=fw_result["meals"][k]; cc_m=cc_result["meals"][k]
            st.markdown(f"### {fw_m['label']}")
            st.caption(fw_m["desc"])
            col_fw,col_cc=st.columns(2)
            with col_fw:
                st.markdown(f"**🪵 Firewood — KES {fw_m['total_cost']:.1f}/student/day**")
                tbl={"Ingredient":[],"Qty":[],"Unit Price":[],"Cost (KES)":[]}
                for ing in fw_m["ingredients"]:
                    tbl["Ingredient"].append(ing["name"]); tbl["Qty"].append(ing["qty"])
                    tbl["Unit Price"].append(ing["price"]); tbl["Cost (KES)"].append(f"{ing['cost']:.2f}")
                st.table(tbl)
                st.markdown(f'<div class="cost-fw">Food: KES {fw_m["food_cost"]:.1f} | '
                            f'Fuel ({int(fw_m["fuel_share"]*100)}%): KES {fw_m["fuel_cost"]:.1f} | '
                            f'Labour ({prices["labour_overhead_pct"]}%): KES {fw_m["labour_cost"]:.1f}</div>',unsafe_allow_html=True)
            with col_cc:
                st.markdown(f"**🔵 {fuel_type} — KES {cc_m['cc_total_cost']:.1f}/student/day**")
                tbl2={"Ingredient":[],"FW Cost":[],"CC Cost":[],"Change":[]}
                for ing in fw_m["ingredients"]:
                    tbl2["Ingredient"].append(ing["name"])
                    tbl2["FW Cost"].append(f"{ing['cost']:.2f}")
                    tbl2["CC Cost"].append(f"{ing['cost']:.2f}")
                    tbl2["Change"].append("—")
                st.table(tbl2)
                fuel_sv=fw_m["fuel_cost"]-cc_m["cc_fuel_cost"]
                st.markdown(f'<div class="cost-cc">Food: KES {cc_m["food_cost"]:.1f} (unchanged) | '
                            f'Fuel ({fuel_type}): KES {cc_m["cc_fuel_cost"]:.1f} | '
                            f'Labour: KES {cc_m["labour_cost"]:.1f}<br>'
                            f'<b>Fuel saving: KES {fuel_sv:.1f}/day ({int(CLEAN_FUEL_SAVE*100)}% reduction)</b></div>',unsafe_allow_html=True)
            sv_d=cc_m["saving_per_day"]
            st.markdown(f"**Daily saving:** KES {sv_d:.1f} → **Weekly:** KES {sv_d*DAYS_PER_WEEK:.0f} → **Term:** KES {sv_d*DAYS_PER_WEEK*WEEKS_PER_TERM:.0f}")
            st.markdown("---")
        st.markdown("#### 📋 Summary — Per Student")
        hcols=st.columns(6)
        for c,h in zip(hcols,["Meal","FW/day","CC/day","Save/day","Save/week","Save/term"]):
            c.markdown(f"**{h}**")
        for k,m in cc_result["meals"].items():
            row=st.columns(6); row[0].markdown(m["label"])
            row[1].markdown(f'<span style="color:#c0392b">KES {m["total_cost"]:.1f}</span>',unsafe_allow_html=True)
            row[2].markdown(f'<span style="color:#1a6b3c">KES {m["cc_total_cost"]:.1f}</span>',unsafe_allow_html=True)
            row[3].markdown(f'<span style="color:#1a6b3c">KES {m["saving_per_day"]:.1f}</span>',unsafe_allow_html=True)
            row[4].markdown(f'<span style="color:#1a6b3c">KES {m["saving_per_day"]*DAYS_PER_WEEK:.0f}</span>',unsafe_allow_html=True)
            row[5].markdown(f'<span style="color:#1a6b3c">KES {m["saving_per_day"]*DAYS_PER_WEEK*WEEKS_PER_TERM:.0f}</span>',unsafe_allow_html=True)

# ══ TAB 3 — FIREWOOD COSTS ════════════════════════════════════
with tab_fw:
    st.markdown('<div class="section-head">🪵 Firewood Cost Analysis</div>',unsafe_allow_html=True)
    st.markdown(f"Method: **{current_fuel}** · KES **{fw_price_kg}/kg** · **{fw_kg_day}kg/day**")
    c1,c2=st.columns(2)
    with c1:
        st.markdown("#### 🏫 Whole School")
        for lbl,val in [("Daily",fw_costs["daily"]),("Weekly",fw_costs["weekly"]),
                        ("Term",fw_costs["term"]),("Annual",fw_costs["annual"])]:
            st.markdown(f'<div class="cost-fw"><span style="font-size:.8rem;color:#7a1a1a">{lbl}</span><br><b style="font-size:1.1rem">KES {val:,.0f}</b></div>',unsafe_allow_html=True)
    with c2:
        st.markdown("#### 👤 Per Student (fuel only)")
        for lbl,val in [("Per day",fw_costs["per_student_day"]),
                        ("Per week",fw_costs["per_student_week"]),
                        ("Per term",fw_costs["per_student_day"]*DAYS_PER_WEEK*WEEKS_PER_TERM)]:
            st.markdown(f'<div class="cost-fw"><span style="font-size:.8rem;color:#7a1a1a">{lbl}</span><br><b style="font-size:1.1rem">KES {val:.1f}</b></div>',unsafe_allow_html=True)
        st.metric("kg/term",f"{fw_kg_day*DAYS_PER_WEEK*WEEKS_PER_TERM:,}kg")
        co2_yr=fw_kg_day*DAYS_PER_WEEK*WEEKS_PER_TERM*3*1.65
        st.metric("CO₂/year",f"{co2_yr/1000:.1f} tonnes",help="IPCC: 1.65 kg CO₂/kg firewood")
    st.divider()
    c1,c2,c3=st.columns(3)
    c1.metric("Firewood fuel/term",f"KES {fw_costs['term']:,.0f}")
    cc_fuel_t=sum(m["cc_fuel_cost"] for m in cc_result["meals"].values())*DAYS_PER_WEEK*WEEKS_PER_TERM*num_students
    fw_fuel_t=sum(m["fuel_cost"] for m in fw_result["meals"].values())*DAYS_PER_WEEK*WEEKS_PER_TERM*num_students
    c2.metric(f"{fuel_type} fuel/term",f"KES {cc_fuel_t:,.0f}",delta=f"-KES {fw_fuel_t-cc_fuel_t:,.0f}")
    c3.metric("Fuel saving/term",f"KES {fw_fuel_t-cc_fuel_t:,.0f}",
              delta=f"{int((fw_fuel_t-cc_fuel_t)/fw_fuel_t*100)}% less" if fw_fuel_t>0 else "")

# ══ TAB 4 — MAP ═══════════════════════════════════════════════
with tab_map_t:
    st.markdown('<div class="section-head">School Location & Energy Infrastructure</div>',unsafe_allow_html=True)
    st.markdown(f'<div class="geo-confirmed">📍 <b>Pinned location:</b> {school_name}, {county}<br>'
                f'<span style="font-family:monospace;font-size:.82rem">Lat: {lat:.5f} | Lng: {lng:.5f}</span>'
                f'</div>',unsafe_allow_html=True)
    cm,cl=st.columns([3,1])
    with cm:
        fmap=folium.Map(location=[lat,lng],zoom_start=15,tiles="CartoDB positron")
        folium.Marker([lat,lng],
            popup=folium.Popup(f"<b>{school_name}</b><br>{county}<br>Students: {num_students:,}<br>"
                               f"Current: {current_fuel}<br>Target: {fuel_type}",max_width=220),
            tooltip=f"📍 {school_name}",icon=folium.Icon(color="green",icon="home",prefix="fa")).add_to(fmap)
        sub=offset_coords(lat,lng,2.0,0)
        folium.Marker(sub,popup="⚡ Substation (~2km)",tooltip="Substation",
            icon=folium.Icon(color="blue",icon="bolt",prefix="fa")).add_to(fmap)
        folium.PolyLine([offset_coords(lat,lng,5,180),[lat,lng],offset_coords(lat,lng,5,0)],
            color="#1a6bcc",weight=3,opacity=0.7,tooltip="Power line corridor").add_to(fmap)
        lpg_pt=offset_coords(lat,lng,3.0,90)
        folium.Marker(lpg_pt,popup="🔵 LPG Depot (~3km)",tooltip="LPG Depot",
            icon=folium.Icon(color="orange",icon="fire",prefix="fa")).add_to(fmap)
        town=offset_coords(lat,lng,4.0,225)
        folium.Marker(town,popup="🏘️ Town (~4km)",tooltip="Town",
            icon=folium.Icon(color="red",icon="building",prefix="fa")).add_to(fmap)
        folium.Circle([lat,lng],radius=5000,color="#1a6b3c",fill=True,fill_opacity=0.05,tooltip="5km zone").add_to(fmap)
        folium.LayerControl().add_to(fmap)
        st_folium(fmap,width=740,height=500)
    with cl:
        st.markdown("**Legend**")
        st.markdown("🟢 School (your pin)  \n🔵 Substation  \n🟠 LPG Depot  \n🔴 Town  \n🔵 Power line  \n⭕ 5km zone")
        st.divider()
        st.markdown("**Location method**")
        st.markdown("📌 User-placed map pin")
        st.markdown(f"Lat: `{lat:.5f}`  \nLng: `{lng:.5f}`")
        st.divider()
        st.markdown('<div class="warning-box">⚠️ Infrastructure markers are indicative. Run Due Diligence for verified utility data.</div>',unsafe_allow_html=True)

# ══ TAB 5 — EQUIPMENT ════════════════════════════════════════
with tab_equip:
    st.markdown('<div class="section-head">📐 Equipment Sizing & Cost</div>',unsafe_allow_html=True)
    cs,cc2=st.columns(2)
    with cs:
        st.markdown("#### 🍲 Pot Allocation")
        st.caption(f"{num_students} × {max(len(served_meals),1)} meals × 5L = {sizing['total_litres']:,}L/day")
        for sz in sorted(sizing["pot_alloc"].keys(),reverse=True):
            cnt=sizing["pot_alloc"][sz]
            st.markdown(f"**{sz}L — {cnt} pot(s)**"); st.progress(min(cnt/8,1.0))
        st.success(f"{sizing['total_pots']} pots | {sizing['stoves']} stoves (+20% buffer)")
    with cc2:
        st.markdown(f"#### 💰 Cost — {fuel_type}")
        for item in equip["items"]:
            ca2,cb2=st.columns([3,1]); ca2.markdown(item["item"]); cb2.markdown(f"**KES {item['total']:,}**")
        st.markdown("---")
        st.markdown(f"### KES {equip['grand']:,}")
        st.caption(f"Amortised: **KES {amort_term:,.0f}/term** · **KES {amort_stu_t:.0f}/student/term**")
    st.divider()
    ca2,cb2=st.columns(2)
    lpg_eq=calc_equip(sizing,"LPG"); elec_eq=calc_equip(sizing,"Electric")
    ca2.metric("LPG Equipment",f"KES {lpg_eq['grand']:,}")
    cb2.metric("Electric Equipment",f"KES {elec_eq['grand']:,}")
    cheaper="LPG" if lpg_eq["grand"]<elec_eq["grand"] else "Electric"
    st.info(f"💡 **{cheaper}** is cheaper by KES {abs(lpg_eq['grand']-elec_eq['grand']):,}")

# ══ TAB 6 — METHODOLOGY ══════════════════════════════════════
with tab_calc:
    st.markdown('<div class="section-head">🧮 Methodology & Data Sources</div>',unsafe_allow_html=True)
    st.markdown("### 🥣 How Meal Costs Are Estimated")
    st.markdown('<div class="calc-step"><b>No fixed price assumptions.</b> Each meal uses real recipe gram quantities × commodity prices. Formula: <code>Ingredient cost = (grams/1000) × price/kg</code>. Labour (20%) and firewood fuel (10-22% by meal) added separately.</div>',unsafe_allow_html=True)
    for k in ["breakfast","lunch","supper"]:
        with st.expander(f"{MEAL_RECIPES[k]['label']} — {MEAL_RECIPES[k]['desc']}"):
            tbl={"Ingredient":[],"Qty":[],"Commodity":[]};
            for ing in MEAL_RECIPES[k]["ingredients"]:
                tbl["Ingredient"].append(COMMODITY_DEFAULTS[ing["commodity"]]["label"])
                tbl["Qty"].append(f"{ing['grams']}{'ml' if '_L' in ing['commodity'] else 'g'}")
                tbl["Commodity"].append(ing["commodity"])
            st.table(tbl)
            m=fw_result["meals"].get(k)
            if m: st.markdown(f"**Calculated: KES {m['total_cost']:.2f}/student/day** (food: {m['food_cost']:.2f} + fuel: {m['fuel_cost']:.2f} + labour: {m['labour_cost']:.2f})")
    st.divider()
    st.markdown("### 📊 Data Sources")
    st.table({
        "Item":["Avg secondary meal","Firewood fuel (lunch)","Clean cooking saving","CO₂/kg firewood","Maize flour","Beans","School calendar"],
        "Value":["KES 38.93/day","22% of food cost","40% reduction","1.65 kg CO₂/kg","~KES 58/kg","~KES 90/kg","3 terms × 13 weeks"],
        "Source":["KIPPRA 2024","Institutional catering","Kenya REA","IPCC","FEWS NET 2024","FEWS NET 2024","Kenya MoE"],
    })
    st.divider()
    st.markdown("### 📍 Geolocation Method")
    st.markdown('<div class="calc-step"><b>User-placed map pin.</b> No external geocoding API. No OSM search. The user zooms in on the interactive Kenya map and clicks their school\'s exact location. Works for any school, anywhere in Kenya.</div>',unsafe_allow_html=True)

# ══ TAB 7 — AI AGENT ══════════════════════════════════════════
with tab_agent:
    st.markdown('<div class="section-head">🤖 CleanCook AI Agent</div>',unsafe_allow_html=True)
    if not openai_key:
        st.warning("⚠️ Enter OpenAI API key in sidebar.")
    else:
        @tool
        def get_meal_costs_tool(meal: str) -> str:
            """Get ingredient-level cost for a specific meal (breakfast, lunch, or supper)."""
            if meal not in fw_result["meals"]:
                return f"Meal not found. Available: {list(fw_result['meals'].keys())}"
            m=fw_result["meals"][meal]; cc=cc_result["meals"][meal]
            lines=[f"{m['label']} — KES {m['total_cost']:.2f}/student/day","Ingredients:"]
            for ing in m["ingredients"]: lines.append(f"  {ing['name']}: {ing['qty']} = KES {ing['cost']:.2f}")
            lines+=[f"Fuel: KES {m['fuel_cost']:.2f} | Labour: KES {m['labour_cost']:.2f}",
                    f"With {fuel_type}: KES {cc['cc_total_cost']:.2f}/day | Saving: KES {cc['saving_per_day']:.2f}/day"]
            return "\n".join(lines)

        @tool
        def get_savings_summary_tool() -> str:
            """Full firewood vs clean cooking savings for this school."""
            return (f"{school_name}, {county} — {num_students} students\n"
                    f"FW meal/student/day: KES {fw_result['daily']:.1f}\n"
                    f"FW meal/student/term: KES {fw_result['term']:.0f}\n"
                    f"{fuel_type} meal/student/term: KES {cc_result['term']:.0f}\n"
                    f"Equipment amort/student/term: KES {amort_stu_t:.0f}\n"
                    f"NET saving/student/term: KES {saving_term:.0f}\n"
                    f"Whole school saving/year: KES {school_sv_yr:,.0f}\n"
                    f"Payback: {equip['grand']/(school_sv_yr if school_sv_yr>0 else 1):.1f} years")

        @tool
        def get_firewood_costs_tool() -> str:
            """Firewood cost breakdown for the school."""
            return (f"KES {fw_price_kg}/kg × {fw_kg_day}kg/day\n"
                    f"Daily: KES {fw_costs['daily']:,.0f}\nWeekly: KES {fw_costs['weekly']:,.0f}\n"
                    f"Term: KES {fw_costs['term']:,.0f}\nAnnual: KES {fw_costs['annual']:,.0f}")

        @tool
        def get_equipment_tool() -> str:
            """Equipment sizing and cost."""
            s=calc_sizing(num_students,max(len(served_meals),1)); e=calc_equip(s,fuel_type)
            lines=[f"Daily litres: {s['total_litres']:,}L","Pots:"]
            for sz,cnt in sorted(s["pot_alloc"].items(),reverse=True): lines.append(f"  {cnt}× {sz}L")
            lines+=[f"Stoves: {s['stoves']}",f"Total: KES {e['grand']:,}",
                    f"Amortised: KES {e['grand']/(EQUIPMENT_LIFE*TERMS_PER_YEAR*num_students):.0f}/student/term"]
            return "\n".join(lines)

        agent_tools=[get_meal_costs_tool,get_savings_summary_tool,get_firewood_costs_tool,get_equipment_tool]
        if tavily_key:
            os.environ["TAVILY_API_KEY"]=tavily_key
            agent_tools.append(TavilySearch(max_results=5,topic="general"))
        os.environ["OPENAI_API_KEY"]=openai_key
        llm=ChatOpenAI(model="gpt-4o",temperature=0.1,openai_api_key=openai_key)
        agent=create_agent(llm,agent_tools,
            system_prompt=(f"You are CleanCook, helping {school_name} ({num_students} students, {county}, Kenya) "
                           f"transition from {current_fuel} to {fuel_type}. "
                           f"Meals: {', '.join(served_meals)}. Firewood: KES {fw_price_kg}/kg, {fw_kg_day}kg/day. "
                           f"Meal costs are estimated from Kenya commodity prices (KIPPRA 2024). Be specific, use KES."),
            name="cleancook_agent")
        for msg in st.session_state.chat_msgs:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
        c1,c2,c3=st.columns(3)
        for col,sug in zip([c1,c2,c3],["What does lunch cost per student?",
                                        f"How much do we save switching to {fuel_type}?",
                                        "What are our firewood costs per term?"]):
            if col.button(sug,key=f"sug_{sug[:8]}"): st.session_state.pending=sug
        prompt=st.chat_input("Ask CleanCook anything...")
        if not prompt and "pending" in st.session_state: prompt=st.session_state.pop("pending")
        if prompt:
            st.session_state.chat_msgs.append({"role":"user","content":prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        res=agent.invoke({"messages":[{"role":"user","content":prompt}]})
                        response=res["messages"][-1].content
                    except Exception as e: response=f"⚠️ Error: {e}"
                st.markdown(response)
                st.session_state.chat_msgs.append({"role":"assistant","content":response})
        if st.button("🗑️ Clear Chat"): st.session_state.chat_msgs=[]; st.rerun()

# ══ TAB 8 — DUE DILIGENCE ════════════════════════════════════
with tab_dd:
    st.markdown('<div class="section-head">🔍 Due Diligence Report</div>',unsafe_allow_html=True)
    st.markdown(f"Live Tavily research on **{school_name}**, **{county}**.")
    if not tavily_key: st.warning("⚠️ Enter Tavily API key in sidebar.")
    elif not openai_key: st.warning("⚠️ Enter OpenAI API key for AI summary.")
    else:
        if st.button("🚀 Run Full Due Diligence",type="primary"):
            os.environ["TAVILY_API_KEY"]=tavily_key; os.environ["OPENAI_API_KEY"]=openai_key
            tav=TavilySearch(max_results=5,topic="general",search_depth="advanced",include_answer=True)
            queries=[(f"{school_name} {county} Kenya school","🏫 School Background"),
                     (f"electricity grid access {county} Kenya","⚡ Electricity Grid"),
                     (f"LPG suppliers {county} Kenya","🔵 LPG Availability"),
                     (f"clean cooking LPG schools Kenya","🌍 Clean Cooking"),
                     (f"firewood cost Kenya {county}","🪵 Firewood Market")]
            dd={}; prog=st.progress(0)
            for i,(q,sec) in enumerate(queries):
                try:
                    raw=tav.invoke({"query":q}); dd[sec]=json.loads(raw) if isinstance(raw,str) else raw
                except Exception as e: dd[sec]={"error":str(e)}
                prog.progress((i+1)/len(queries))
            st.markdown(f"## Report: {school_name}"); st.divider()
            for sec,data in dd.items():
                st.markdown(f"### {sec}")
                if "error" in data: st.error(data["error"]); continue
                if data.get("answer"):
                    st.markdown(f'<div class="dd-card"><b>Summary:</b> {data["answer"]}</div>',unsafe_allow_html=True)
                for r in data.get("results",[])[:3]:
                    snip=r.get("content","")[:280]
                    if snip:
                        st.markdown(f'<div class="dd-card"><b>{r.get("title","")}</b><br>{snip}...'
                                    f'<div class="dd-source">🔗 <a href="{r.get("url","")}" target="_blank">{r.get("url","")}</a>'
                                    f' | Score: {r.get("score",0):.2f}</div></div>',unsafe_allow_html=True)
            st.divider(); st.markdown("### 🤖 AI Summary")
            with st.spinner("Generating..."):
                try:
                    ctx="\n".join(f"{s}: "+" | ".join(r.get("content","")[:150] for r in d.get("results",[])[:2])
                        for s,d in dd.items() if "error" not in d)
                    llm_dd=ChatOpenAI(model="gpt-4o",temperature=0.1,openai_api_key=openai_key)
                    summary=llm_dd.invoke(f"Due diligence for {school_name}, {county}. {fuel_type} transition. "
                        f"{num_students} students. {current_fuel} at KES {fw_price_kg}/kg.\n\n{ctx}\n\n"
                        f"6-8 bullets: school viability, grid/LPG access, firewood market, risks, recommendation.")
                    st.markdown(summary.content)
                except Exception as e: st.error(f"Error: {e}")

st.markdown("---")
st.markdown("<div style='text-align:center;color:#aaa;font-size:.8rem'>"
            "CleanCook v6 · Map pin geolocation · KIPPRA 2024 · FEWS NET · MoE 2025 · LangChain + Tavily"
            "</div>",unsafe_allow_html=True)
