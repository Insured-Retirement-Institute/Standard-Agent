# Archive — Previous Agent Versions

These files are retained for reference only. DO NOT USE for production.

## Version History
- **v1** (agent_v1.py, tools_v1.py, app_v1.py) — 16 tools, heavy deps (ruamel, openapi-spec-validator, jsonschema)
- **v2** (agent_v2.py, tools_v2.py, app_v2.py) — 6 I/O tools. Scored 78/100 calibrated.
- **v3** (agent_v3.py) — Zero tools. Scored 87/100 calibrated.

## Production Agent
Use `agent/agent_prod.py` — combines v3's calibrated prompt with 2 fetch tools.
Run via `app_prod.py` (port 8000).
