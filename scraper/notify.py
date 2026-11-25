"""Manda una notifica push con il riepilogo degli annunci nuovi non ancora notificati."""
import json
import os

from pywebpush import webpush, WebPushException

from common import sb

VAPID_PRIVATE = os.environ["VAPID_PRIVATE_KEY"]          # chiave privata (base64url, formato raw)
VAPID_SUB = (os.environ.get("VAPID_SUBJECT") or "").strip()
# Deve essere "mailto:..." o "https://...": altrimenti la firma delle notifiche fallisce.
if VAPID_SUB and "@" in VAPID_SUB and not VAPID_SUB.startswith("mailto:"):
    VAPID_SUB = "mailto:" + VAPID_SUB
if VAPID_SUB.startswith("https://"):
    VAPID_SUB = "https://" + VAPID_SUB[8:].split("/")[0]   # solo schema + host, senza percorso
if not VAPID_SUB.startswith(("mailto:", "https://")):
    VAPID_SUB = "https://xxfumexx.github.io"


def main():
    rows = sb("annunci", params={"select": "id,d", "notificato": "eq.false", "limit": "500"}) or []
    if not rows:
        print("nessuna novità")
        return
    att = [r for r in rows if r["d"].get("stato") not in ("Scartato", "Non più disponibile")]
    solo = [r for r in att if r["d"].get("perChi") != "due"]
    due = [r for r in att if r["d"].get("perChi") == "due" or r["d"].get("dueStanzeLibere")]
    tgt = [r for r in solo if (r["d"].get("prezzo") or 1e9) <= 700] + \
          [r for r in att if r["d"].get("perChi") == "due" and (r["d"].get("prezzo") or 1e9) <= 1400]
    if att:
        parts = [f"{len(att)} {'nuovo annuncio' if len(att) == 1 else 'nuovi annunci'}"]
        if tgt:
            parts.append(f"{len(tgt)} in target")
        if due:
            parts.append(f"{len(due)} per due")
        best = sorted(tgt or att, key=lambda r: r["d"].get("prezzo") or 1e9)[0]["d"]
        body = " · ".join(parts) + f". Es.: {best.get('indirizzo') or best.get('titolo')}, CHF {best.get('prezzo')}"
        payload = json.dumps({"title": "Casa St. Gallen", "body": body[:180], "tag": "nuovi", "url": "./"})
        subs = sb("push_sub", params={"select": "endpoint,sub"}) or []
        sent = 0
        for s in subs:
            try:
                webpush(subscription_info=s["sub"], data=payload, vapid_private_key=VAPID_PRIVATE,
                        vapid_claims={"sub": VAPID_SUB}, ttl=6 * 3600)
                sent += 1
            except WebPushException as e:
                code = getattr(e.response, "status_code", None)
                if code in (404, 410):      # iscrizione scaduta: la tolgo
                    sb("push_sub", "DELETE", params={"endpoint": "eq." + s["endpoint"]})
                else:
                    print("push error", code)
        print(f"notifica inviata a {sent}/{len(subs)} dispositivi: {body}")
    ids = ",".join(f'"{r["id"]}"' for r in rows)
    sb("annunci", "PATCH", {"notificato": True}, prefer="return=minimal", params={"id": f"in.({ids})"})


if __name__ == "__main__":
    main()
