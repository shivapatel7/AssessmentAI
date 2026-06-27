# AI Travel Planner

A multi-agent travel planning system built with **LangGraph**, **FastAPI**, **Groq** (LLM), and **Exa** (web search). A user submits travel preferences; the system researches the destination, drafts a day-by-day itinerary, pauses for human approval, and produces a final plan only after sign-off.

## Architecture

```
                ┌──────────────────────────────────────────────┐
                │              LangGraph StateGraph             │
                │                                                │
  POST /plan ──▶│  research ──▶ plan ──▶ human_review (interrupt)│
                │                 ▲            │                 │
                │                 │     ┌──────┼──────┐          │
                │            reject│  approve modify  │          │
                │                 │     │      │      │          │
                │                 └─────┘   modify ───┘          │
                │                     finalize ──▶ END           │
                └──────────────────────────────────────────────┘
                         state persisted via MemorySaver
                         (thread_id == plan_id)
```

**Orchestrator** — a LangGraph `StateGraph` that validates the request, routes between stages, drives the HITL interrupt, and emits the final plan. Workflow state is held in a checkpointer keyed by `plan_id`, so the graph can pause at the review step and resume later across separate HTTP requests.

**Agent 1 — Research Agent** (`create_react_agent`)
- `web_search` (Exa) — real-time destination research: attractions, safety, local tips
- `get_weather` (Open-Meteo, no key required) — current conditions + 5-day forecast

**Agent 2 — Itinerary Planner Agent** (`create_react_agent`)
- `allocate_budget` — splits the budget across lodging/food/activities/transport/buffer
- `generate_packing_list` — packing list tailored to destination, interests, and season

**Human-in-the-Loop** — after the planner produces a draft, the graph hits `interrupt()` and pauses. The user submits a review:
- **approve** → finalize
- **reject** + comments → routes back to the planner for revision, then pauses again
- **modify** + modifications → applies targeted edits (e.g. swap a day's activities), then pauses again for re-approval

## Project Structure

```
app/
  main.py      FastAPI app + endpoints
  graph.py     LangGraph orchestrator (nodes, edges, HITL interrupt)
  agents.py    Research and Planner ReAct agents
  tools.py     web_search, get_weather, allocate_budget, generate_packing_list
  llm.py       Groq LLM factory
  state.py     Pydantic request/review models + graph state
requirements.txt
.env.example
```

## Setup

1. Create and activate a virtual environment, then install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   # source .venv/bin/activate   # macOS/Linux
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your keys:
   ```
   GROQ_API_KEY=...      # https://console.groq.com
   EXA_API_KEY=...       # https://exa.ai
   GROQ_MODEL=llama-3.3-70b-versatile
   ```
   (Weather uses Open-Meteo, which needs no key.)

## Run

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for interactive Swagger docs.

## API

| Method | Endpoint            | Purpose                                  |
|--------|---------------------|------------------------------------------|
| POST   | `/plan`             | Submit a travel request, returns plan ID |
| GET    | `/plan/{id}`        | Current stage, research, and draft plan  |
| POST   | `/plan/{id}/review` | Submit HITL feedback (approve/reject/modify) |
| GET    | `/plan/{id}/final`  | Finalized plan (only after approval)     |

### Example

**Create a plan**
```bash
curl -X POST http://localhost:8000/plan -H "Content-Type: application/json" -d '{
  "destination": "Rome, Italy",
  "start_date": "2026-09-10",
  "end_date": "2026-09-13",
  "budget_min": 1200,
  "budget_max": 1800,
  "interests": ["history", "food", "photography"],
  "travelers": 2
}'
```
```json
{
  "plan_id": "a1b2c3d4-...",
  "stage": "awaiting_review",
  "draft_plan": {
    "summary": "...",
    "days": [{"day": 1, "date": "2026-09-10", "title": "Ancient Rome", "activities": ["Colosseum", "Roman Forum"], "meals": ["Trattoria lunch"], "estimated_cost": 220}],
    "budget_breakdown": {"lodging": 600, "food": 375, "activities": 300, "local_transport": 150, "buffer": 75},
    "packing_list": ["Passport / ID", "Comfortable walking shoes", "Camera and spare batteries"],
    "notes": "..."
  }
}
```

**Approve**
```bash
curl -X POST http://localhost:8000/plan/<id>/review -H "Content-Type: application/json" \
  -d '{"action": "approve"}'
```

**Reject with feedback** (re-plans, then pauses again)
```bash
curl -X POST http://localhost:8000/plan/<id>/review -H "Content-Type: application/json" \
  -d '{"action": "reject", "comments": "Too packed — make day 2 more relaxed and add a food tour."}'
```

**Modify a specific day** (then pauses again for re-approval)
```bash
curl -X POST http://localhost:8000/plan/<id>/review -H "Content-Type: application/json" \
  -d '{"action": "modify", "modifications": [{"day": 2, "activities": ["Vatican Museums", "St. Peter'\''s Basilica"]}]}'
```

**Get final plan**
```bash
curl http://localhost:8000/plan/<id>/final
```

## Design Decisions & Tradeoffs

- **LangGraph `interrupt()` + `MemorySaver` checkpointer** is the backbone of HITL. `thread_id == plan_id` means the workflow truly persists across the pause: `POST /review` resumes the exact paused graph with `Command(resume=feedback)`, rather than re-running from scratch. This directly satisfies the "persist state across the pause" criterion.
- **ReAct agents** (`create_react_agent`) let the LLM decide when to call tools, keeping agent logic small while staying genuinely agentic.
- **Structured draft plan as JSON** makes the `modify` action precise — edits target a day by number and merge fields, rather than regenerating everything.
- **Open-Meteo for weather** avoids an extra API key and gives real forecast data.
- **In-memory state** (`MemorySaver` + a set of plan IDs) keeps the prototype simple. It is not durable across restarts.

## What I'd Improve With More Time / Production Concerns

- **Durable persistence** — swap `MemorySaver` for a Postgres/SQLite checkpointer so plans survive restarts and scale across workers.
- **Async + background execution** — research/planning can take seconds; run the graph in a background task and have `POST /plan` return immediately with `stage: processing`, polled via `GET /plan/{id}`.
- **Auth, rate limiting, and per-user scoping** on plan IDs.
- **Retries / fallbacks** for tool and LLM failures, plus structured output validation (e.g. Pydantic-parsed plans with retry on malformed JSON).
- **Observability** — tracing (LangSmith) and token/cost logging per request.
- **Smarter reject routing** — currently reject re-runs the planner; with more time it could decide whether fresh research is needed before re-planning.

### Assumptions

- One reviewer per plan; review actions are sequential.
- Dates are passed as `YYYY-MM-DD` strings and are not validated against a calendar.
- Budget is interpreted as total trip budget (range), and the planner aims near its midpoint.
