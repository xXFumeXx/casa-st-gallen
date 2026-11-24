"""Funzioni condivise: accesso a Supabase con la chiave di servizio (solo lato server)."""
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
UA = "Mozilla/5.0 (casa-st-gallen-app)"


def http_json(url, method="GET", body=None, headers=None, timeout=40):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": UA, **(headers or {})})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def sb(path, method="GET", body=None, prefer=None, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    h = {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"}
    if prefer:
        h["Prefer"] = prefer
    return http_json(url, method, body, h)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_check(agente, nuovi, nuovi_target, sparsi, siti, siti_ko, nota):
    d = {"quando": now_iso(), "agente": agente, "nuovi": nuovi, "nuoviInTarget": nuovi_target,
         "sparsi": sparsi, "siti": siti, "sitiKo": siti_ko, "note": nota}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    sb("controlli", "POST", [{"id": "ultimo", "d": d}, {"id": f"giro-{stamp}-{agente}", "d": d}],
       prefer="resolution=merge-duplicates,return=minimal")
