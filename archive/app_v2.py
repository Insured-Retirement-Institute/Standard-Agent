"""
IRI Standards Agent v2 — Minimal Tools Test Server
Run with: python app_v2.py

This version uses only 6 I/O tools (fetch + lookup). All validation,
style checking, structural analysis, and scoring is done by the LLM.
No ruamel, no openapi-spec-validator, no jsonschema required.
"""
import os
import sys
import traceback

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List

# ── Load .env if python-dotenv is installed ────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[server-v2] Loaded .env file", flush=True)
except ImportError:
    pass  # python-dotenv is optional

app = FastAPI(title="IRI Standards Agent v2 (Minimal Tools)")

# ── Load agent at startup ──────────────────────────────────────────────────
iri_agent = None
startup_error = None

try:
    from agent.agent_v2 import create_agent_v2
    iri_agent = create_agent_v2()
except Exception as e:
    startup_error = str(e)
    print(f"[server-v2] Agent init failed: {e}", flush=True)
    traceback.print_exc()


# ── Request/Response models ────────────────────────────────────────────────
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    input: List[Message]


# ── Routes ─────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def chat_ui():
    return """<!DOCTYPE html>
<html><head><title>IRI Standards Agent v2</title>
<style>
  body { font-family: system-ui; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #1a1a2e; color: #eee; }
  h1 { color: #ff9f43; }
  .badge { background: #ff9f43; color: #000; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
  #chat { border: 1px solid #333; border-radius: 8px; padding: 20px; min-height: 300px; max-height: 500px;
          overflow-y: auto; background: #16213e; margin-bottom: 15px; white-space: pre-wrap; }
  .user { color: #ff9f43; margin: 10px 0; }
  .agent { color: #e0e0e0; margin: 10px 0; border-left: 3px solid #ff9f43; padding-left: 12px; }
  .error { color: #ff6b6b; }
  #input-row { display: flex; gap: 10px; }
  input { flex: 1; padding: 12px; border-radius: 6px; border: 1px solid #333; background: #0f3460; color: #eee; font-size: 14px; }
  button { padding: 12px 24px; border-radius: 6px; border: none; background: #ff9f43; color: #000; cursor: pointer; font-weight: bold; }
  button:hover { background: #e08b30; }
  button:disabled { background: #555; cursor: wait; }
  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #ff9f43;
             border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style></head><body>
<h1>IRI Standards Agent v2 <span class="badge">LLM-DRIVEN</span></h1>
<p>OpenAPI 3.1 validation via LLM reasoning — 6 I/O tools only (fetch + lookup).</p>
<div id="chat"></div>
<div id="input-row">
  <input id="msg" placeholder="Paste YAML or ask about IRI specs..." onkeydown="if(event.key==='Enter')send()">
  <button onclick="send()" id="btn">Send</button>
</div>
<script>
const chat = document.getElementById('chat');
async function send() {
  const input = document.getElementById('msg');
  const btn = document.getElementById('btn');
  const msg = input.value.trim();
  if (!msg) return;
  chat.innerHTML += '<div class="user"><b>You:</b> ' + msg.replace(/</g,'&lt;') + '</div>';
  input.value = '';
  btn.disabled = true;
  chat.innerHTML += '<div class="agent" id="loading"><div class="spinner"></div> Thinking...</div>';
  chat.scrollTop = chat.scrollHeight;
  try {
    const res = await fetch('/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({input: [{role: 'user', content: msg}]})
    });
    const data = await res.json();
    document.getElementById('loading').remove();
    chat.innerHTML += '<div class="agent"><b>Agent:</b> ' + (data.output||data.detail||'No response').replace(/</g,'&lt;') + '</div>';
  } catch(e) {
    document.getElementById('loading').remove();
    chat.innerHTML += '<div class="error">Error: ' + e.message + '</div>';
  }
  btn.disabled = false;
  chat.scrollTop = chat.scrollHeight;
}
</script></body></html>"""


@app.get("/health")
def health():
    return {
        "status": "running",
        "version": "v2-minimal-tools",
        "agent_ready": iri_agent is not None,
        "tools": 6,
        "tools_list": ["fetch_yaml_from_url", "fetch_data_dictionary",
                       "list_available_specs", "get_endpoint_schema",
                       "get_schema_definition", "list_schema_names"],
        "error": startup_error,
    }


@app.post("/chat")
def chat(request: ChatRequest):
    """Chat endpoint — send a message, get an agent response."""
    if not iri_agent:
        return {"output": f"Agent not initialized: {startup_error}"}

    user_msg = ""
    for msg in reversed(request.input):
        if msg.role == "user":
            user_msg = msg.content
            break
    if not user_msg:
        return {"output": "No user message found."}

    try:
        result = iri_agent(user_msg)
        return {"output": str(result)}
    except Exception as e:
        return {"output": f"Agent error: {str(e)}"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8001"))
    print(f"[server-v2] Starting LLM-DRIVEN agent on http://localhost:{port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port)
