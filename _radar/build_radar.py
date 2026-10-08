#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MARA Combined-Radar – Cloud-Generator (Steuer + KI), Service-Variante
=====================================================================
Baut aus zwei JSON-Dateien eine fertige Radar-Seite für eine Kanzlei,
prüft sie und legt sie im Repo ab:

    <kanzlei>/index.html                 ← immer die aktuelle Ausgabe (Live-Link)
    <kanzlei>/archiv/KW<NN>-<JJJJ>.html  ← Archivkopie
    <kanzlei>/version.json               ← KW/Stand für die Start-Seite auf dem Stick

Aufruf (aus dem Repo-Wurzelordner):
    python3 _radar/build_radar.py --kanzlei intertreu \
        --steuer /pfad/items_kw_steuer.json --ki /pfad/items_kw_ki.json

    python3 _radar/build_radar.py --kanzlei intertreu --dump-previous /pfad/prev.json
        → schreibt die Items der aktuell veröffentlichten Ausgabe als JSON
          (für Dubletten-Abgleich und Dauerthemen)

Bricht mit Exit-Code 1 ab, wenn die Prüfung fehlschlägt – dann wird NICHTS
überschrieben und die letzte gute Ausgabe bleibt online.
"""

import argparse, json, os, re, shutil, subprocess, sys, tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
TEMPLATE = os.path.join(HERE, "MARA-Combined-TEMPLATE.html")

PRIOS = {"dringend", "relevant", "info"}
STEUER_KAT = {"Gesetz", "BMF", "BFH", "Digital", "Frist", "Änderung", "Verband"}
KI_KAT = {"Frontier-Modell", "Open Source", "Tools/Agenten", "Regulatorik",
          "Infrastruktur", "Mittelstand-Praxis", "Risiko/Warnung"}
MANDANTEN = {"GmbH", "GbR", "Freiberufler", "Arbeitnehmer", "Immobilien", "Gemeinnützig"}


def fail(msg):
    sys.exit(f"❌ ABBRUCH: {msg}\n   Es wurde nichts veröffentlicht – die letzte Ausgabe bleibt online.")


# ---------------------------------------------------------------- Prüfung Daten
def check_items(data, label, kind):
    problems = []
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return [f"{label}: keine Items vorhanden"]
    ids = set()
    for i, it in enumerate(items, 1):
        p = f"{label} Item {i}"
        for key in ("id", "kat", "name", "prio", "desc", "quelle"):
            if key not in it or it[key] in (None, ""):
                problems.append(f"{p}: Feld '{key}' fehlt")
        if it.get("id") in ids:
            problems.append(f"{p}: doppelte id {it.get('id')}")
        ids.add(it.get("id"))
        if it.get("prio") not in PRIOS:
            problems.append(f"{p}: ungültige prio '{it.get('prio')}'")
        q = it.get("quelle") or {}
        if not str(q.get("url", "")).startswith("http"):
            problems.append(f"{p}: Quelle ohne gültige URL")
        if kind == "steuer":
            if it.get("kat") not in STEUER_KAT:
                problems.append(f"{p}: unbekannte Kategorie '{it.get('kat')}'")
            bad = set(it.get("mandanten", [])) - MANDANTEN
            if bad:
                problems.append(f"{p}: unbekannte Mandantentypen {sorted(bad)}")
            f = it.get("frist")
            if f and not re.search(r"\d{2}\.\d{2}\.\d{4}", str(f)):
                # Freitext ist erlaubt, erscheint dann aber nicht in der Fristen-Ampel
                print(f"ℹ️  {p}: Frist ohne Datum ('{f}') – nicht in der Fristen-Ampel")
        else:
            if it.get("kat") not in KI_KAT:
                problems.append(f"{p}: unbekannte Kategorie '{it.get('kat')}'")
    return problems


# ---------------------------------------------------------------- Serialisierung
def js(v):
    return json.dumps(v, ensure_ascii=False)


def ser_steuer(items):
    parts = []
    for it in items:
        parts.append(
            "  { id:%s, kat:%s, ebene:%s, name:%s, prio:%s, frist:%s, mandanten:%s, "
            "update:%s, desc:%s, handlung:%s, quelle:{name:%s,url:%s} }" % (
                js(it["id"]), js(it["kat"]), js(it.get("ebene", "")), js(it["name"]),
                js(it["prio"]), js(it["frist"]) if it.get("frist") else "null",
                js(it.get("mandanten", [])), "true" if it.get("update") else "false",
                js(it["desc"]), js(it.get("handlung", "")),
                js(it["quelle"]["name"]), js(it["quelle"]["url"])))
    return "let items = [\n" + ",\n".join(parts) + "\n];"


def ser_ki(items):
    parts = []
    for it in items:
        parts.append(
            "  { id:%s, kat:%s, name:%s, prio:%s, update:%s, desc:%s, einordnung:%s, "
            "quelle:{name:%s,url:%s} }" % (
                js(it["id"]), js(it["kat"]), js(it["name"]), js(it["prio"]),
                "true" if it.get("update") else "false", js(it["desc"]),
                js(it.get("einordnung", "")), js(it["quelle"]["name"]), js(it["quelle"]["url"])))
    return "let itemsKI = [\n" + ",\n".join(parts) + "\n];"


# ---------------------------------------------------------------- Bauen
def build(steuer, ki, kanzlei_name):
    kw = int(steuer.get("kw") or ki.get("kw"))
    monat = steuer.get("monat") or ki.get("monat")
    datum = steuer.get("datum") or ki.get("datum")
    if not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", datum or ""):
        fail(f"Datum fehlt oder falsches Format: '{datum}'")
    year = datum[-4:]

    with open(TEMPLATE, encoding="utf-8") as f:
        html = f.read()

    rep = {
        "/* MARA_KW_HEADER */": f"KW {kw} · {monat}",
        "/* MARA_TITLE_KW */": f"KW {kw} · {year}",
        "/* MARA_KW_NUM */": str(kw),
        "/* MARA_KW_EMAIL */": f"KW {kw} / {monat}",
        "/* MARA_STAND */": datum,
        "/* MARA_DATUM */": f"Stand: {datum}",
        "/* MARA_KW_DISCLAIMER */": f"KW {kw}/{year}",
        "let items = [/* MARA_ITEMS_PLACEHOLDER */];": ser_steuer(steuer["items"]),
        "let itemsKI = [/* MARA_ITEMS_KI_PLACEHOLDER */];": ser_ki(ki["items"]),
    }
    for k, v in rep.items():
        if k not in html:
            fail(f"Platzhalter im Template nicht gefunden: {k}")
        html = html.replace(k, v)

    # Kleinere Korrekturen für den Service-Betrieb
    html = html.replace('id="rtMonat" value="April 2026"', f'id="rtMonat" value="{monat}"')
    if kanzlei_name:
        html = html.replace(
            '<div class="subtitle">Steuer-News · KI-News · Mandanten-Selektion · Personalisierter Email-Versand</div>',
            f'<div class="subtitle">für {kanzlei_name} · Steuer-News · KI-News · Mandanten-Email</div>', 1)

    # Maschinenlesbare Kopie der Daten (für Dubletten-Abgleich nächste Woche)
    meta = {"kw": kw, "monat": monat, "datum": datum,
            "steuer": steuer["items"], "ki": ki["items"]}
    if steuer.get("kurzfassung"):
        meta["kurzfassung"] = steuer["kurzfassung"]
    payload = json.dumps(meta,
                         ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("</head>",
                        f'<meta name="mara-version" content="KW{kw}-{year}">\n'
                        f'<script type="application/json" id="mara-data">{payload}</script>\n</head>', 1)
    return html, kw, year, datum, monat


def check_html(html):
    if "/* MARA_" in html:
        fail("Im Ergebnis stehen noch unersetzte Platzhalter.")
    # JavaScript-Syntax mit Node prüfen (alle Inline-Skripte ohne type-Attribut)
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.S)
    if not scripts:
        fail("Kein JavaScript-Block gefunden.")
    if shutil.which("node"):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
            t.write("\n;\n".join(scripts))
        r = subprocess.run(["node", "--check", t.name], capture_output=True, text=True)
        os.unlink(t.name)
        if r.returncode != 0:
            fail("JavaScript-Syntaxfehler:\n" + r.stderr[-800:])
    else:
        print("⚠️  node nicht verfügbar – JS-Syntaxprüfung übersprungen")


def write_archiv_index(base):
    """Liste aller Archivausgaben für das Auswahlmenü auf der Seite."""
    adir = os.path.join(base, "archiv")
    out = []
    for fn in os.listdir(adir):
        m = re.fullmatch(r"KW(\d{2})-(\d{4})\.html", fn)
        if not m:
            continue
        stand = ""
        try:
            head = open(os.path.join(adir, fn), encoding="utf-8").read()
            d = re.search(r'id="mara-data">\{"kw": \d+, "monat": "[^"]*", "datum": "(\d{2}\.\d{2}\.\d{4})"', head)
            stand = d.group(1) if d else ""
        except OSError:
            pass
        out.append({"datei": fn, "kw": int(m.group(1)), "jahr": int(m.group(2)), "stand": stand})
    out.sort(key=lambda x: (x["jahr"], x["kw"]), reverse=True)
    with open(os.path.join(adir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


def dump_previous(kanzlei, out):
    path = os.path.join(REPO, kanzlei, "index.html")
    if not os.path.exists(path):
        print("ℹ️  Noch keine veröffentlichte Ausgabe – erster Lauf.")
        json.dump({"kw": None, "steuer": [], "ki": []}, open(out, "w", encoding="utf-8"))
        return
    html = open(path, encoding="utf-8").read()
    m = re.search(r'<script type="application/json" id="mara-data">(.*?)</script>', html, re.S)
    if not m:
        fail("Vorausgabe enthält keinen mara-data-Block.")
    data = json.loads(m.group(1).replace("<\\/", "</"))
    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"✅ Vorausgabe KW {data['kw']} gelesen: {len(data['steuer'])} Steuer-, {len(data['ki'])} KI-Items → {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kanzlei", required=True, help="Ordnername im Repo, z. B. intertreu")
    ap.add_argument("--kanzlei-name", default="", help="Anzeigename im Untertitel")
    ap.add_argument("--steuer")
    ap.add_argument("--ki")
    ap.add_argument("--dump-previous")
    ap.add_argument("--dry-run", action="store_true", help="nur bauen und prüfen, nichts ablegen")
    a = ap.parse_args()

    if a.dump_previous:
        return dump_previous(a.kanzlei, a.dump_previous)
    if not (a.steuer and a.ki):
        fail("--steuer und --ki werden benötigt")

    steuer = json.load(open(a.steuer, encoding="utf-8"))
    ki = json.load(open(a.ki, encoding="utf-8"))
    problems = check_items(steuer, "Steuer", "steuer") + check_items(ki, "KI", "ki")
    kurz = steuer.get("kurzfassung")
    if kurz is not None and (not isinstance(kurz, list) or not all(isinstance(t, str) and t.strip() for t in kurz) or len(kurz) > 5):
        problems.append("Steuer: 'kurzfassung' muss eine Liste mit 1–5 Texten sein (oder ganz fehlen)")
    if len(steuer.get("items", [])) < 8:
        problems.append(f"Steuer: nur {len(steuer.get('items', []))} Items (mind. 8 erwartet)")
    if len(ki.get("items", [])) < 3:
        problems.append(f"KI: nur {len(ki.get('items', []))} Items (mind. 3 erwartet)")
    if problems:
        fail("Datenprüfung fehlgeschlagen:\n   - " + "\n   - ".join(problems))

    html, kw, year, datum, monat = build(steuer, ki, a.kanzlei_name)
    check_html(html)

    if a.dry_run:
        print(f"✅ Probebau KW {kw}/{year} ok ({len(html):,} Zeichen) – nichts abgelegt.")
        return

    base = os.path.join(REPO, a.kanzlei)
    os.makedirs(os.path.join(base, "archiv"), exist_ok=True)
    with open(os.path.join(base, "archiv", f"KW{kw:02d}-{year}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(base, "version.json"), "w", encoding="utf-8") as f:
        json.dump({"kw": kw, "jahr": int(year), "stand": datum, "monat": monat,
                   "steuer_items": len(steuer["items"]), "ki_items": len(ki["items"]),
                   "erstellt": datetime.now().isoformat(timespec="minutes")},
                  f, ensure_ascii=False, indent=1)
    write_archiv_index(base)
    print(f"✅ KW {kw}/{year} gebaut und geprüft: {a.kanzlei}/index.html + archiv/KW{kw:02d}-{year}.html")
    print(f"   Steuer-Items: {len(steuer['items'])} | KI-Items: {len(ki['items'])} | {len(html):,} Zeichen")


if __name__ == "__main__":
    main()
