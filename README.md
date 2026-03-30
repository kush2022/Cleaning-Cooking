# Clean Cooking Streamlit App

A Streamlit app for clean cooking analysis and insights.

## Requirements

- Python 3.10+
- pip

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run the app

```bash
streamlit run src/clean_cooking_app.py
```

## How the app works

- **Enter API keys** in the sidebar (OpenAI + Tavily) to enable AI features.
- **Set school details** (name, county, students, meals/day, fuel target, budget).
- **Confirm location**:
  - Search OpenStreetMap and pick the correct result, **or**
  - Enter exact latitude/longitude manually.
  - The main app only unlocks after location confirmation.
- **Review outputs** across tabs:
  - **School Map**: confirmed school pin plus indicative infrastructure markers.
  - **Sizing & Costs**: pot allocation, stove count, cost breakdown, budget gap.
  - **How Calculations Work**: formulas and assumptions used.
  - **AI Agent**: ask questions about sizing and cost scenarios.
  - **Due Diligence**: live web research and AI summary.

## Project structure

- `src/clean_cooking_app.py` — Streamlit UI entry point.
- `src/clean_cooking.py` — Core logic/utilities.



<!-- Notes -->

Per meal per student 
the cost of the fireword 
incase there is LPG 
The savings from transition from firewood to LPG 
