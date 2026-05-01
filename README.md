# IRI Standards Agent

**OpenAPI 3.1 YAML Standardization Agent** for IRI Digital-First API specifications.

Validates, creates, and updates OpenAPI specs using the IRI Data Dictionary, DFA Style Guide, and active IRI portal specs — with a 100-point governance scorecard and hallucination resistance.

This agent runs anywhere Python 3.10+ is available.

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/your-org/Standard-Agent.git
cd Standard-Agent

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
cp .env.example .env
#    Edit .env and set your OPENAI_API_KEY (see options below)

# 5. Start the agent
python app.py
```

Open **http://localhost:8000** in your browser to use the chat UI.

## API Key Configuration

The agent works with **any OpenAI-compatible API**. Edit your `.env` file with one of:

| Provider | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `MODEL_ID` |
|---|---|---|---|
| **OpenAI** | `sk-...` | *(leave unset)* | `gpt-4o` |
| **Azure OpenAI** | Your Azure key | `https://your-resource.openai.azure.com/...` | Your deployment name |
| **Databricks** | Personal access token (`dapi...`) | `https://your-workspace.databricks.net/serving-endpoints` | `databricks-claude-sonnet-4` |

See `.env.example` for full details.

## Project Structure

```
Standard-Agent/
├── app.py                  # FastAPI server + chat UI (entry point)
├── agent/                  # Agent package
│   ├── agent.py            # Agent creation (portable, no cloud deps)
│   ├── tools.py            # 13 programmatic tools for OpenAPI validation
│   └── system_prompt.py    # System prompt with governance rules
├── draft-api-specs/        # Working group draft specifications
├── requirements.txt        # Python dependencies
├── .env.example            # API key configuration template
├── .gitignore
├── LICENSE
└── README.md
```

## Agent Capabilities

### 4 Operating Modes

| Mode | Trigger | Output |
|---|---|---|
| **UPDATE** | Provide existing YAML | Patch + updated YAML |
| **BUILD** | Provide Data Dictionary (no YAML) | New OpenAPI 3.1 YAML |
| **VALIDATE** | Provide YAML + "validate only" | Governance scorecard |
| **COMPARE** | Provide two versions | Diff analysis |

### 13 Tools

**Programmatic Validation (6)**
- `validate_openapi_structure` — OpenAPI 3.1 structural validation
- `parse_yaml_safely` — YAML-to-JSON parsing
- `emit_yaml` — JSON-to-YAML conversion
- `check_style_guide_rules` — IRI DFA Style Guide checks
- `compute_dd_coverage` — Data Dictionary coverage analysis
- `generate_scorecard` — 100-point governance scorecard

**Multi-Part Assembly (2)**
- `manage_multipart_assembly` — State manager for large YAML uploads
- `get_assembled_yaml` — Retrieve assembled content

**Lookup (5)**
- `list_available_specs` — List loaded IRI specifications
- `get_endpoint_schema` — Get request/response schema for an endpoint
- `get_schema_definition` — Get a schema from components
- `validate_payload_against_schema` — Validate JSON against a schema
- `list_schema_names` — List all schemas in a spec

### Governance Scorecard (100 pts)

| Category | Weight |
|---|---|
| A) OpenAPI 3.1 Conformance | 30 pts |
| B) IRI DFA Style Guide | 25 pts |
| C) DD Coverage & Fidelity | 25 pts |
| D) Evidence & Traceability | 10 pts |
| E) Operational Readiness | 10 pts |

**Gates:** PASS ≥ 85 (no critical fails) · CONDITIONAL 70–84 · FAIL < 70 or any critical fail

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Chat UI (open in browser) |
| `GET` | `/health` | Health check |
| `POST` | `/chat` | Send a message to the agent |

### Example: curl

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "What IRI specs do you know about?"}]}'
```

### Example: Python

```python
import requests

response = requests.post("http://localhost:8000/chat", json={
    "input": [{"role": "user", "content": "Validate this OpenAPI spec: ..."}]
})
print(response.json()["output"])
```

## Draft API Specifications

The working group's draft OpenAPI specifications are in the [draft-api-specs](./draft-api-specs) directory. Once reviewed and approved by the [Governance Committee](https://www.irionline.org/member-programs/operations-technology/committee-hub/governance/), they are moved to the [Digital-First-Specifications](https://github.com/Insured-Retirement-Institute/Digital-First-Specifications) repository and published at [specs.dfa.irionline.org](https://specs.dfa.irionline.org).

## How to Engage

- Please contact the business owners or IRI (hpikus@irionline.org) to get added to working group discussions or have feedback on the agent.
- Security issues and bugs should be reported to Katherine Dease (kdease@irionline.org).
- See the [Digital-First-Specifications](https://github.com/Insured-Retirement-Institute/Digital-First-Specifications) repository for the code of conduct and standards governance workflow.
