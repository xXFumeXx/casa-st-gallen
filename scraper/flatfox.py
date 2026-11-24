"""Scarica gli annunci in affitto di Flatfox a St. Gallen e aggiunge solo quelli nuovi.

Usa l'API pubblica che la mappa di flatfox.ch usa nel browser. Non contatta nessuno e
non salva nomi o testi personali degli inserzionisti: solo i dati strutturati.
"""
import re
from datetime import date

from common import http_json, sb, log_check

API = "https://flatfox.ch/api/v1"
# Città di St. Gallen divisa in 3x3 riquadri (l'API restituisce al massimo 400 punti per richiesta).
N, S, W, E = 47.465, 47.385, 9.27, 9.46
CATS = {"SHARED", "APARTMENT", "HOUSE"}
LIMIT_DATE = date(2027, 3, 1)       # oltre: ingresso troppo tardi per il semestre
PERIOD_END = date(2027, 6, 30)
SERVIZI = {
    "washingmachine": "Lavatrice", "tumbler": "Asciugatrice", "dishwasher": "Lavastoviglie",
    "balconygarden": "Balcone o giardino", "broadbandinternet": "Internet veloce", "elevator": "Ascensore",
    "petsallowed": "Animali ammessi", "parkingspace": "Parcheggio", "garage": "Garage",
}
ONE_GENDER = re.compile(r"\b(mitbewohnerin\b|nur\s+(für\s+)?frauen|frauen-?wg|weibliche?\s+mitbewohner|female\s+only|women\s+only|girls?\s+only)", re.I)


def pins():
    out = {}
    lat_step, lon_step = (N - S) / 3, (E - W) / 3
    for i in range(3):
        for j in range(3):
            q = f"{API}/pin/?north={N - i*lat_step}&south={N - (i+1)*lat_step}&west={W + j*lon_step}&east={W + (j+1)*lon_step}&max_count=400"
            for p in http_json(q) or []:
                if p.get("price_unit") == "monthly" and (p.get("price_display") or 0) >= 250:
                    out[p["pk"]] = p
    return out


def details(pks):
    res = []
    pks = list(pks)
    for k in range(0, len(pks), 50):
        url = f"{API}/public-listing/?" + "&".join(f"pk={p}" for p in pks[k:k+50])
        while url:
            j = http_json(url)
            res += j.get("results", [])
            url = j.get("next")
    return res


def rooms(x):
    try:
        return float(x["number_of_rooms"]) if x.get("number_of_rooms") else None
    except ValueError:
        return None


def to_doc(x, today):
    if x.get("offer_type") != "RENT" or x.get("object_category") not in CATS or x.get("status") != "act":
        return None
    r = rooms(x)
    cat = x["object_category"]
    if cat == "SHARED" or x.get("object_type") == "SINGLE_ROOM":
        tipo, per = "stanza", "solo"
    elif r is not None and r >= 2.5:
        tipo, per = "appartamento", "due"
    else:
        tipo, per = ("monolocale" if (r or 1) <= 1.5 else "appartamento"), "solo"
    mdt, md = x.get("moving_date_type"), x.get("moving_date")
    dal = today.isoformat() if mdt == "imm" else (md if mdt == "dat" else None)
    if dal and date.fromisoformat(dal) > LIMIT_DATE:
        return None
    price = x.get("rent_gross") or x.get("price_display")
    net, charges = x.get("rent_net"), x.get("rent_charges")
    desc = (x.get("description") or "") + " " + (x.get("description_title") or "")
    fascia, note = "", []
    if ONE_GENDER.search(desc):
        fascia = "Da verificare"
        note.append("Il testo sembra cercare solo donne: verificare prima di scrivere.")
    if tipo == "appartamento" and r == 2.5:
        fascia = "Da verificare"
        note.append("2.5 locali: verificare che ci siano 2 camere da letto separate.")
    if mdt == "agr":
        note.append("Data di ingresso da concordare.")
    elif mdt == "imm":
        note.append("Disponibile subito: chiedere se si può entrare il 1° febbraio.")
    street = x.get("street")
    addr = f"{street}, {x.get('zipcode') or ''}".strip(", ") if street else (x.get("public_address") or "St. Gallen")
    services = [SERVIZI[a["name"]] for a in x.get("attributes") or [] if a.get("name") in SERVIZI]
    pid = f"flatfox:{x['pk']}"
    title = x.get("description_title") or x.get("short_title") or x.get("public_title")
    return pid, {
        "titolo": title, "indirizzo": addr, "zona": None, "tipo": tipo, "perChi": per,
        "dueStanzeLibere": False, "prezzoDue": None,
        "mq": x.get("surface_living"), "prezzo": price,
        "prezzoNota": (f"{net} affitto + {charges} spese" if net and charges else None),
        "dal": dal, "fino": None, "finoTesto": "A tempo" if x.get("is_temporary") else None,
        "contratto": "a tempo" if x.get("is_temporary") else None,
        "spese": "incluse" if (x.get("rent_gross") or x.get("price_display_type") == "TOTAL") else None,
        "cauzione": None, "unaTantum": None,
        "arredato": "sì" if x.get("is_furnished") else None, "registrazione": None,
        "coinquilini": None, "coinqProfilo": None, "coinqEta": None, "lingue": None, "bagno": None,
        "servizi": services,
        "casa": (f"Appartamento {x['number_of_rooms']} locali" if tipo == "appartamento" and r else ("Stanza in WG" if tipo == "stanza" else None)),
        "lat": x.get("latitude"), "lon": x.get("longitude"), "posApprox": not bool(street),
        "stato": "Da aprire", "fascia": fascia, "motivo": None,
        "prossimo": "Aprire l'annuncio e leggere coinquilini, durata e condizioni",
        "note": " ".join(note) or None,
        "fonte": "Flatfox", "link": "https://flatfox.ch" + x["url"].replace("/en/", "/de/"),
        "mappaLink": None, "idAnnuncio": pid,
        "scoperto": today.isoformat(), "importato": today.isoformat(), "agente": "github",
    }


def main():
    today = date.today()
    existing = {r["id"]: r["d"] for r in (sb("annunci", params={"select": "id,d", "id": "like.flatfox:*", "limit": "5000"}) or [])}
    pin = pins()
    new_pks = [pk for pk in pin if f"flatfox:{pk}" not in existing]
    rows = []
    for x in details(new_pks):
        doc = to_doc(x, today)
        if doc:
            rows.append({"id": doc[0], "d": doc[1]})
    inserted = []
    for k in range(0, len(rows), 100):
        inserted += sb("annunci", "POST", rows[k:k+100],
                       prefer="resolution=ignore-duplicates,return=representation", params={"on_conflict": "id"}) or []

    # Annunci spariti: controllo quelli ancora "da aprire/contattare" non più tra i punti della mappa.
    gone = 0
    check = [i for i, d in existing.items() if d.get("stato") in ("Da aprire", "Da contattare") and int(i.split(":")[1]) not in pin]
    if check:
        alive = {f"flatfox:{x['pk']}" for x in details(int(i.split(":")[1]) for i in check) if x.get("status") == "act"}
        for i in check:
            if i not in alive:
                sb("rpc/patch_annuncio", "POST", {"p_id": i, "p_patch": {"stato": "Non più disponibile", "motivo": f"Rimosso da Flatfox il {today.strftime('%d.%m.%Y')}"}})
                gone += 1

    def in_target(d):
        p = d.get("prezzo") or 99999
        return p <= (1400 if d.get("perChi") == "due" else 700)
    nt = sum(1 for r in inserted if in_target(r["d"]))
    log_check("github", len(inserted), nt, gone, ["Flatfox"], [], f"Flatfox: {len(pin)} offerte in zona, {len(inserted)} nuove salvate.")
    print(f"pins={len(pin)} new_candidates={len(new_pks)} inserted={len(inserted)} in_target={nt} gone={gone}")


if __name__ == "__main__":
    main()
