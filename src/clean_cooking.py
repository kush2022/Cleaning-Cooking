"""
CleanCook Agent
===============
A LangChain agent that helps schools size and cost their transition
from firewood cooking to clean energy (LPG or Electric).

Built strictly using:
- https://docs.langchain.com/oss/python/langchain/agents
- https://docs.langchain.com/oss/python/langchain/tools

Requirements:
    pip install langchain langchain-openai langgraph

Usage:
    export OPENAI_API_KEY=your_key
    python cleancook_agent.py
"""

from dataclasses import dataclass
from langchain.tools import tool, ToolRuntime
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file (for OPENAI_API_KEY)



# ─────────────────────────────────────────────
# RUNTIME CONTEXT
# Passed at invocation time — immutable per session.
# Docs: https://docs.langchain.com/oss/python/langchain/tools#context
# ─────────────────────────────────────────────

@dataclass
class SchoolContext:
    """Immutable context passed at invocation time."""
    school_name: str = "Unknown School"
    county: str = "Kenya"


# ─────────────────────────────────────────────
# TOOL 1: size_cooking_equipment
# Uses @tool decorator as per docs.
# Type hints are required — they define the tool's input schema.
# Docs: https://docs.langchain.com/oss/python/langchain/tools#basic-tool-definition
# ─────────────────────────────────────────────

@tool
def size_cooking_equipment(
    num_students: int,
    meals_per_day: int = 3,
    runtime: ToolRuntime = None,
) -> str:
    """
    Calculate the recommended cooking pot sizes for a school based on
    the number of students and meals per day.

    Returns a breakdown of pot sizes (50L, 100L, 200L) needed
    to meet daily cooking demand, using 5 litres per student per meal
    as the baseline (sourced from Machakos High School data).

    Args:
        num_students: Total number of students to cook for.
        meals_per_day: Number of meals cooked daily (1, 2, or 3).
    """
    if num_students <= 0:
        return "Error: Number of students must be greater than 0."
    if meals_per_day not in [1, 2, 3]:
        return "Error: meals_per_day must be 1, 2, or 3."

    # Benchmark: 5 litres per student per meal (Machakos baseline)
    litres_per_student_per_meal = 5
    total_litres = num_students * meals_per_day * litres_per_student_per_meal

    # Pot sizing — fill to 80% capacity for safety
    pot_sizes = [200, 100, 50]
    pot_fill_ratio = 0.8
    allocation = {}
    remaining = total_litres

    for size in pot_sizes:
        usable = size * pot_fill_ratio
        count = int(remaining // usable)
        if count > 0:
            allocation[size] = count
            remaining -= count * usable

    # Round up any remainder into a 50L pot
    if remaining > 0:
        allocation[50] = allocation.get(50, 0) + 1

    total_pots = sum(allocation.values())
    stoves_needed = int(total_pots * 1.2)  # 20% redundancy buffer

    lines = [
        f"📊 Cooking Equipment Sizing Report",
        f"{'─' * 40}",
        f"Total daily volume required : {total_litres:,} litres",
        f"",
        f"Recommended pot allocation:",
    ]
    for size, count in sorted(allocation.items(), reverse=True):
        lines.append(f"  • {count}x {size}L pot(s)")

    lines += [
        f"",
        f"Total pots needed  : {total_pots}",
        f"Stoves recommended : {stoves_needed} (includes 20% redundancy)",
        f"Benchmark used     : {litres_per_student_per_meal}L per student per meal",
        f"                     (sourced from Machakos High School data)",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# TOOL 2: estimate_transition_cost
# Uses Pydantic-style type hints for complex input.
# Docs: https://docs.langchain.com/oss/python/langchain/tools#advanced-schema-definition
# ─────────────────────────────────────────────

@tool
def estimate_transition_cost(
    num_students: int,
    fuel_type: str,
    meals_per_day: int = 3,
    runtime: ToolRuntime = None,
) -> str:
    """
    Estimate the total cost (in KES) for a school to transition from
    firewood to clean cooking — either LPG or Electric.

    Provides a line-item cost breakdown covering:
    - Cooking stoves/burners
    - Pots (stainless steel)
    - Installation and infrastructure
    - Total cost estimate

    Args:
        num_students: Total number of students.
        fuel_type: Target fuel type — must be 'lpg' or 'electric'.
        meals_per_day: Number of meals cooked per day (1, 2, or 3).
    """
    fuel_type = fuel_type.lower().strip()
    if fuel_type not in ["lpg", "electric"]:
        return "Error: fuel_type must be 'lpg' or 'electric'."
    if num_students <= 0:
        return "Error: num_students must be greater than 0."

    # ── Sizing (same logic as size_cooking_equipment) ──
    total_litres = num_students * meals_per_day * 5
    pot_sizes = [200, 100, 50]
    allocation = {}
    remaining = total_litres

    for size in pot_sizes:
        usable = size * 0.8
        count = int(remaining // usable)
        if count > 0:
            allocation[size] = count
            remaining -= count * usable
    if remaining > 0:
        allocation[50] = allocation.get(50, 0) + 1

    total_pots = sum(allocation.values())
    stoves_needed = int(total_pots * 1.2)

    # ── Cost tables (KES) ──
    stove_costs = {
        "lpg": {200: 35_000, 100: 22_000, 50: 14_000},
        "electric": {200: 55_000, 100: 38_000, 50: 22_000},
    }
    pot_costs = {200: 28_000, 100: 16_000, 50: 9_000}
    infra_costs = {
        "lpg": {"name": "LPG cylinders (45kg) + regulator set", "per_stove": 18_000},
        "electric": {"name": "3-phase wiring & panel upgrade", "per_stove": 25_000},
    }
    install_rate = {"lpg": 0.15, "electric": 0.20}

    stove_total = 0
    pot_total = 0
    lines = [
        f"💰 Transition Cost Estimate — {fuel_type.upper()}",
        f"{'─' * 45}",
        f"School size   : {num_students:,} students",
        f"Meals/day     : {meals_per_day}",
        f"",
        f"{'Item':<40} {'KES':>10}",
        f"{'─' * 52}",
    ]

    for size, count in sorted(allocation.items(), reverse=True):
        sc = stove_costs[fuel_type][size]
        pc = pot_costs[size]
        stove_line = sc * count
        pot_line = pc * count
        stove_total += stove_line
        pot_total += pot_line
        label = "LPG burner" if fuel_type == "lpg" else "Induction cooker"
        lines.append(f"  {count}x {label} ({size}L){'':<18} {stove_line:>10,}")
        lines.append(f"  {count}x Stainless pot ({size}L){'':<18} {pot_line:>10,}")

    infra = infra_costs[fuel_type]
    infra_total = infra["per_stove"] * stoves_needed
    stove_total += infra_total
    lines.append(f"  {infra['name'][:38]:<38} {infra_total:>10,}")

    install_total = int((stove_total + pot_total) * install_rate[fuel_type])
    grand_total = stove_total + pot_total + install_total

    lines += [
        f"{'─' * 52}",
        f"  Equipment subtotal{'':<22} {stove_total:>10,}",
        f"  Pots subtotal{'':<27} {pot_total:>10,}",
        f"  Installation ({int(install_rate[fuel_type]*100)}%){'':<25} {install_total:>10,}",
        f"{'═' * 52}",
        f"  TOTAL ESTIMATED COST (KES){'':<15} {grand_total:>10,}",
        f"",
        f"  Cost per student : KES {grand_total // num_students:,}",
        f"  Note: Excludes kitchen construction. Equipment only.",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# TOOL 3: compare_fuel_options
# A convenience tool that calls both fuel scenarios side-by-side.
# ─────────────────────────────────────────────

@tool
def compare_fuel_options(
    num_students: int,
    meals_per_day: int = 3,
) -> str:
    """
    Compare the estimated transition costs for LPG vs Electric cooking
    side by side, for a given school size.

    Useful when a school hasn't decided on a fuel type yet and wants
    to evaluate both options before committing.

    Args:
        num_students: Total number of students.
        meals_per_day: Number of meals per day (1, 2, or 3).
    """
    lpg_result = estimate_transition_cost.invoke({
        "num_students": num_students,
        "fuel_type": "lpg",
        "meals_per_day": meals_per_day,
    })
    electric_result = estimate_transition_cost.invoke({
        "num_students": num_students,
        "fuel_type": "electric",
        "meals_per_day": meals_per_day,
    })
    return (
        f"{'═' * 52}\n"
        f"COMPARISON: LPG vs ELECTRIC\n"
        f"{'═' * 52}\n\n"
        f"{lpg_result}\n\n"
        f"{'─' * 52}\n\n"
        f"{electric_result}"
    )


# ─────────────────────────────────────────────
# TOOL 4: get_benchmark_data
# Returns the Machakos baseline data used for sizing.
# ─────────────────────────────────────────────

@tool
def get_benchmark_data(runtime: ToolRuntime = None) -> str:
    """
    Return the benchmark cooking data used to calibrate this tool,
    sourced from Machakos High School in Machakos County, Kenya.

    Includes pot sizes in use, number of students, and the derived
    litres-per-student-per-meal figure used for all calculations.
    """
    # Access school context if available (injected at invocation time)
    school = "Machakos High School"
    county = "Machakos County"

    if runtime and runtime.context:
        school = runtime.context.school_name
        county = runtime.context.county

    return (
        f"📋 Benchmark Reference Data\n"
        f"{'─' * 40}\n"
        f"Source school  : {school}\n"
        f"County         : {county}\n"
        f"\n"
        f"Firewood equipment currently in use:\n"
        f"  • 1x 1,000L pot\n"
        f"  • 1x 500L pot\n"
        f"  • 3x 200L pots\n"
        f"\n"
        f"Derived benchmark:\n"
        f"  5 litres of food/water per student per meal\n"
        f"\n"
        f"This baseline is used for all sizing and cost calculations."
    )


# ─────────────────────────────────────────────
# CREATE THE AGENT
# Uses create_agent() as documented.
# Docs: https://docs.langchain.com/oss/python/langchain/agents
# ─────────────────────────────────────────────

model = ChatOpenAI(
    model="gpt-4.1-mini",
    temperature=0.1,
)

tools = [
    size_cooking_equipment,
    estimate_transition_cost,
    compare_fuel_options,
    get_benchmark_data,
]

# System prompt shapes agent behaviour — passed as a plain string per docs
SYSTEM_PROMPT = """You are CleanCook, an expert assistant helping Catholic schools
in Kenya transition from firewood cooking to clean energy (LPG or electric).

Your job is to:
1. Help schools understand the size of cooking equipment they need
2. Estimate the cost of transitioning their cooking setup
3. Compare LPG vs electric options when asked
4. Always reference the Machakos High School benchmark when explaining calculations

Be concise, accurate, and practical. All costs are in Kenyan Shillings (KES).
When a user provides a school name and number of students, always start by
sizing the equipment, then provide costs unless they specify otherwise.
"""

agent = create_agent(
    model,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    name="cleancook_agent",
    context_schema=SchoolContext,
)


# ─────────────────────────────────────────────
# EXAMPLE INVOCATIONS
# Docs: https://docs.langchain.com/oss/python/langchain/agents#invocation
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("CleanCook Agent — School Energy Transition Tool")
    print("=" * 60)

    # Example 1: Size equipment for a school
    print("\n▶ Example 1: Equipment sizing for 500 students\n")
    result = agent.invoke(
        {"messages": [{"role": "user", "content": (
            "We are St. Mary's Catholic School in Machakos. "
            "We have 500 boarding students and cook 3 meals a day. "
            "What cooking equipment do we need?"
        )}]},
        context=SchoolContext(school_name="St. Mary's Catholic School", county="Machakos"),
    )
    print(result["messages"][-1].content)

    # Example 2: Get cost estimate
    print("\n" + "─" * 60)
    print("\n▶ Example 2: LPG transition cost\n")
    result = agent.invoke(
        {"messages": [{"role": "user", "content": (
            "How much will it cost us to switch to LPG? We have 500 students, 3 meals a day."
        )}]},
        context=SchoolContext(school_name="St. Mary's Catholic School", county="Machakos"),
    )
    print(result["messages"][-1].content)

    # Example 3: Compare fuel options
    print("\n" + "─" * 60)
    print("\n▶ Example 3: Compare LPG vs Electric\n")
    result = agent.invoke(
        {"messages": [{"role": "user", "content": (
            "Compare LPG and electric options for our school of 800 students cooking 3 meals a day."
        )}]},
        context=SchoolContext(school_name="Holy Cross Secondary", county="Nairobi"),
    )
    print(result["messages"][-1].content)

    # Example 4: Show benchmark data
    print("\n" + "─" * 60)
    print("\n▶ Example 4: Show benchmark data\n")
    result = agent.invoke(
        {"messages": [{"role": "user", "content": (
            "Where does your sizing data come from? Show me the benchmark."
        )}]},
    )
    print(result["messages"][-1].content)