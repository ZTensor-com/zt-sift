#!/usr/bin/env python3
"""Local web page for trying the Presidio-only detector by hand.

    ../.venv/bin/python -m tools.web            # then open http://127.0.0.1:8765

Paste or type text, adjust the threshold, and see the detections highlighted in place and listed in a table.
The server listens on 127.0.0.1 only (this machine), makes no outside requests, and does not store or log the text.
"""
import os
import sys
import time
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from pii_detector.detector import detect, load_analyzer

HOST, PORT = "127.0.0.1", int(os.environ.get("PORT", "8765"))
state = {}

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Presidio tester</title>
<style>
  :root { --bg:#fafaf9; --fg:#1c1917; --muted:#78716c; --card:#fff; --line:#e7e5e4; --accent:#2563eb; }
  @media (prefers-color-scheme: dark) { :root { --bg:#161513; --fg:#f5f5f4; --muted:#a8a29e; --card:#1f1d1b; --line:#3a3633; --accent:#60a5fa; } }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
  main { max-width:980px; margin:0 auto; padding:24px 16px 64px; }
  h1 { font-size:20px; margin:0 0 4px; } p.sub { margin:0 0 16px; color:var(--muted); }
  textarea { width:100%; min-height:170px; padding:12px; border:1px solid var(--line); border-radius:8px; background:var(--card);
             color:var(--fg); font:14px/1.5 ui-monospace,Menlo,Consolas,monospace; resize:vertical; }
  .bar { display:flex; flex-wrap:wrap; gap:12px 20px; align-items:center; margin:12px 0; }
  label { display:flex; gap:8px; align-items:center; color:var(--muted); font-size:14px; }
  input[type=number] { width:70px; padding:4px 6px; border:1px solid var(--line); border-radius:6px; background:var(--card); color:var(--fg); }
  button { padding:8px 16px; border:0; border-radius:8px; background:var(--accent); color:#fff; font:inherit; font-weight:600; cursor:pointer; }
  button.ghost { background:transparent; color:var(--muted); border:1px solid var(--line); font-weight:500; }
  #status { color:var(--muted); font-size:14px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px; margin-top:12px; }
  #marked { white-space:pre-wrap; word-break:break-word; font:14px/1.9 ui-monospace,Menlo,Consolas,monospace; }
  mark { padding:2px 3px; border-radius:4px; color:inherit; }
  mark sup { font:600 10px system-ui; margin-left:3px; opacity:.75; }
  table { width:100%; border-collapse:collapse; font-size:13.5px; } th,td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:600; } td.num { font-variant-numeric:tabular-nums; } td code { font:13px ui-monospace,Menlo,monospace; }
  .err { color:#dc2626; }
</style></head><body><main>
<h1>Presidio tester</h1>
<p class="sub">Presidio + spaCy en_core_web_lg only. Runs on this machine; the text is not stored or sent anywhere.</p>
<textarea id="text" spellcheck="false" placeholder="Paste or type text here, then press Detect (Ctrl/Cmd + Enter)"></textarea>
<div class="bar">
  <button id="go">Detect</button><button id="clear" class="ghost">Clear</button><button id="sample" class="ghost">Load sample</button>
  <label>Threshold <input id="threshold" type="number" min="0" max="1" step="0.05" value="0.5"></label>
  <label><input id="collapse" type="checkbox"> best result where they overlap</label>
  <span id="status"></span>
</div>
<div id="out" hidden>
  <div class="card"><div id="marked"></div></div>
  <div class="card"><table><thead><tr><th>Entity</th><th>Text</th><th>Start</th><th>End</th><th>Score</th><th>Recognizer</th></tr></thead><tbody id="rows"></tbody></table></div>
</div>
</main>
<script>
const $ = id => document.getElementById(id);
const SAMPLE = __SAMPLE__;
const esc = s => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function hue(name) { let h = 0; for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }
function colour(name) { const dark = matchMedia('(prefers-color-scheme: dark)').matches;
  return `hsl(${hue(name)} ${dark ? 55 : 80}% ${dark ? 30 : 84}%)`; }
async function run() {
  $('status').className = ''; $('status').textContent = 'Detecting...';
  try {
    const r = await fetch('/detect', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text:$('text').value, threshold:parseFloat($('threshold').value), collapse:$('collapse').checked})});
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.statusText);
    render($('text').value, data);
  } catch (e) { $('status').className = 'err'; $('status').textContent = e.message; }
}
function render(text, data) {
  // Highlight the union; the table preserves the individual classifications.
  const chars = Array.from(text), placed = [];
  for (const d of [...data.detections].sort((a, b) => a.start - b.start || b.end - a.end)) {
    const last = placed[placed.length - 1];
    if (last && d.start < last.end) {
      last.end = Math.max(last.end, d.end);
      if (!last.entity.split(' / ').includes(d.entity)) last.entity += ' / ' + d.entity;
      last.score = Math.max(last.score, d.score);
    } else placed.push({...d});
  }
  let html = '', at = 0;
  for (const d of placed) {
    html += esc(chars.slice(at, d.start).join('')) + `<mark style="background:${colour(d.entity)}" title="${esc(d.entity)} ${d.score}">` +
            esc(chars.slice(d.start, d.end).join('')) + `<sup>${esc(d.entity)}</sup></mark>`;
    at = d.end;
  }
  $('marked').innerHTML = html + esc(chars.slice(at).join(''));
  $('rows').innerHTML = data.detections.map(d => `<tr><td><mark style="background:${colour(d.entity)}">${esc(d.entity)}</mark></td>` +
    `<td><code>${esc(d.text)}</code></td><td class="num">${d.start}</td><td class="num">${d.end}</td>` +
    `<td class="num">${d.score.toFixed(2)}</td><td>${esc(d.recognizer)}</td></tr>`).join('') ||
    '<tr><td colspan="6">No detections.</td></tr>';
  $('out').hidden = false;
  $('status').textContent = `${data.detections.length} detections in ${data.milliseconds} ms`;
}
$('go').onclick = run;
$('clear').onclick = () => { $('text').value = ''; $('out').hidden = true; $('status').textContent = ''; $('text').focus(); };
$('sample').onclick = () => { $('text').value = SAMPLE; run(); };
$('text').addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') run(); });
</script></body></html>"""


async def index(request):
    import json
    sample = open(os.path.join(os.path.dirname(__file__), "..", "samples", "sample_us.txt"), encoding="utf-8").read().strip()
    return HTMLResponse(PAGE.replace("__SAMPLE__", json.dumps(sample)))


async def analyse(request):
    try:
        body = await request.json()
        text, threshold = body["text"], float(body.get("threshold", 0.5))
        if not isinstance(text, str) or not 0 <= threshold <= 1:
            raise ValueError
    except Exception:
        return JSONResponse({"error": "Send JSON like {\"text\": \"...\", \"threshold\": 0.5}"}, status_code=400)
    if len(text) > 3_000_000:
        return JSONResponse({"error": "Text is limited to 3,000,000 characters here"}, status_code=413)
    started = time.time()
    found = detect(state["analyzer"], text, threshold, collapse=bool(body.get("collapse"))) if text.strip() else []
    return JSONResponse({"detections": found, "milliseconds": round((time.time() - started) * 1000)})


@asynccontextmanager
async def lifespan(app):
    state["analyzer"] = load_analyzer()
    detect(state["analyzer"], "warm-up")
    print(f"Ready: http://{HOST}:{PORT}", flush=True)
    yield


app = Starlette(routes=[Route("/", index), Route("/detect", analyse, methods=["POST"])], lifespan=lifespan)

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
    sys.exit(0)
