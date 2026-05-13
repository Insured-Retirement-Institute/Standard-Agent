# IRI Standards Agent — Production v1.0

**OpenAPI 3.1 YAML Standardization Agent** for IRI Digital-First API specifications.

Validates, creates, and updates OpenAPI specs using the IRI Data Dictionary, DFA Style Guide, and approved IRI specs — with a 100-point governance scorecard and hallucination resistance.

---

## Architecture

Production v1.0 uses a **calibrated LLM prompt** with only 2 fetch tools. All validation, style checking, and scoring is performed by the LLM reasoning engine — not programmatic validators.

| Component | Purpose |
|---|---|
| `agent/agent_prod.py` | Production agent — calibrated prompt + 2 tools |
| `agent/tools_prod.py` | `fetch_yaml_from_url`, `fetch_data_dictionary` |
| `app_prod.py` | FastAPI server (port 8000) with chat UI |

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url>
cd Standard-Agent

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure credentials (see Configuration below)
cp .env.example .env
# Edit .env with your API key and endpoint

# 5. Start the agent
python app_prod.py
```

Open **http://localhost:8000** in your browser to use the chat UI.

---

## Configuration

The agent connects to any **OpenAI-compatible API endpoint** (e.g., Azure OpenAI, Anthropic via proxy, or any LLM gateway that exposes the `/chat/completions` interface).

| Environment Variable | Description | Required |
|---|---|---|
| `OPENAI_API_KEY` | API key for the LLM endpoint | Yes |
| `OPENAI_BASE_URL` | Base URL for the OpenAI-compatible endpoint (e.g., `https://your-host/v1`) | Yes |
| `MODEL_ID` | Model identifier to use | No (default: `databricks-claude-opus-4-7`) |
| `PORT` | Server port | No (default: `8000`) |

Create a `.env` file in the project root (see `.env.example`) or export these variables in your shell.

> **Managed compute environments**: If running inside a workspace with SDK-based auth (e.g., a notebook or managed app), the agent will auto-discover credentials from the workspace context. No manual env vars needed.

---

## Project Structure

```
Standard-Agent/
├── app_prod.py                 # FastAPI server + chat UI (entry point)
├── agent/                      # Agent package
│   ├── __init__.py             # Re-exports create_agent
│   ├── agent_prod.py           # Production agent (calibrated prompt + tools)
│   └── tools_prod.py           # 2 fetch tools (URL + Data Dictionary)
├── draft-api-specs/            # Working group draft specifications
├── output/                     # Generated corrected YAML specs
├── benchmarks/                 # Scoring benchmarks for calibration
├── archive/                    # Previous agent versions (DO NOT USE)
│   ├── README.md               # Version history
│   └── agent/                  # v1, v2, v3 agent files
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
├── LICENSE
└── README.md
```

---

## Agent Capabilities

### 4 Operating Modes

| Mode | Trigger | Output |
|---|---|---|
| **VALIDATE** | Provide YAML + "validate only" | Governance scorecard |
| **UPDATE** | Provide existing YAML + change request | Corrected YAML + scorecard |
| **BUILD** | Provide Data Dictionary (no YAML) | New OpenAPI 3.1 YAML |
| **COMPARE** | Provide two versions | Diff analysis |

### 2 Production Tools

| Tool | Purpose |
|---|---|
| `fetch_yaml_from_url` | Download YAML from GitHub or any public URL |
| `fetch_data_dictionary` | Download and parse Excel/CSV Data Dictionary files |

All validation logic (structural, style guide, cross-spec consistency, conditional logic) is performed by the LLM using the calibrated system prompt — no programmatic validators.

### Governance Scorecard (100 pts)

| Category | Weight |
|---|---|
| A) OpenAPI 3.1 Conformance | 30 pts |
| B) IRI DFA Style Guide | 25 pts |
| C) Cross-Spec Consistency | 25 pts |
| D) Evidence & Traceability | 10 pts |
| E) Operational Readiness | 10 pts |

**Gates:** PASS ≥ 85 (no critical fails) · CONDITIONAL 70–84 · FAIL < 70 or any critical fail

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Chat UI (open in browser) |
| `GET` | `/health` | Health check + version info |
| `POST` | `/chat` | Send a message to the agent |

### Example: curl

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "Validate this OpenAPI spec: ..."}]}'
```

### Example: Python

```python
from agent import create_agent

agent = create_agent()
result = agent("Review this OpenAPI 3.1 YAML for IRI compliance: ...")
print(result)
```

---

## Version History

| Version | Architecture | Score | Notes |
|---|---|---|---|
| **v1.0 (production)** | Calibrated prompt + 2 fetch tools | 87/100 | Best accuracy, minimal deps |
| v3 (archived) | Zero tools, pure LLM | 87/100 | No URL fetch capability |
| v2 (archived) | 6 I/O tools | 78/100 | Over-reports cross-spec issues |
| v1 (archived) | 16 tools, heavy deps | — | Could not run (missing deps) |

---

## Draft API Specifications

The working group's draft OpenAPI specifications are in the [draft-api-specs](./draft-api-specs) directory. Once reviewed and approved by the [Governance Committee](https://www.irionline.org/member-programs/operations-technology/committee-hub/governance/), they are moved to the [Digital-First-Specifications](https://github.com/Insured-Retirement-Institute/Digital-First-Specifications) repository and published at [specs.dfa.irionline.org](https://specs.dfa.irionline.org).

---

## How to Engage

- Contact IRI (hpikus@irionline.org) to join working group discussions or provide feedback on the agent.
- Security issues and bugs should be reported to Katherine Dease (kdease@irionline.org).
- See the [Digital-First-Specifications](https://github.com/Insured-Retirement-Institute/Digital-First-Specifications) repository for the code of conduct and standards governance workflow.
