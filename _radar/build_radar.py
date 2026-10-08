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


# ---------------------------------------------------------------- Audio-Leiste
# Liest zur Laufzeit version.json (Wochen-Briefing) und ansage.json (optionale
# Ansage der Kanzleileitung). Fehlt etwas oder ist die Seite offline geöffnet,
# bleibt der jeweilige Knopf einfach unsichtbar.
AUDIO_BAR = r'''<!-- ══ AUDIO ══ -->
<style>
.mara-audio{display:none;background:#3d0f0f;color:#fff;padding:10px 40px;gap:12px;align-items:center;flex-wrap:wrap}
.mara-audio.on{display:flex}
.ma-btn{display:none;align-items:center;gap:10px;border:1px solid rgba(255,255,255,.28);background:rgba(255,255,255,.1);color:#fff;border-radius:999px;padding:7px 16px 7px 8px;font:600 .86rem 'Segoe UI',Arial,sans-serif;cursor:pointer}
.ma-btn.on{display:inline-flex}
.ma-btn:hover{background:rgba(255,255,255,.18)}
.ma-ico{width:30px;height:30px;border-radius:50%;background:#fff;color:#6B1A1A;display:grid;place-items:center;font-size:.8rem;flex:none}
.ma-sub{font-weight:400;opacity:.8;font-size:.78rem}
.ma-ansage{background:#E9A23B;border-color:#E9A23B;color:#2a1600}
.ma-ansage:hover{background:#f2b456}
.ma-ansage .ma-ico{color:#8a4b00}
.ma-prog{flex:1;min-width:140px;height:4px;background:rgba(255,255,255,.2);border-radius:2px;display:none;cursor:pointer}
.ma-prog.on{display:block}
.ma-prog i{display:block;height:100%;width:0;background:#fff;border-radius:2px}
.ma-text{flex-basis:100%;display:none;font-size:.85rem;opacity:.92;padding:2px 0 2px 4px}
.ma-text.on{display:block}
@media(max-width:700px){.mara-audio{padding:10px 16px}}
</style>
<div class="mara-audio" id="maraAudio">
  <button class="ma-btn" id="maBrief" onclick="maraPlay('brief')"><span class="ma-ico" id="maBriefIco">▶</span><span>Wochen-Briefing anhören <span class="ma-sub" id="maBriefSub"></span></span></button>
  <button class="ma-btn ma-ansage" id="maAns" onclick="maraPlay('ansage')"><span class="ma-ico" id="maAnsIco">📣</span><span id="maAnsLabel">Ansage</span></button>
  <div class="ma-prog" id="maProg"><i id="maBar"></i></div>
  <div class="ma-text" id="maAnsText"></div>
  <audio id="maPlayer" preload="none"></audio>
</div>
<script>
(function(){
  var src={brief:null,ansage:null}, cur=null, P=document.getElementById('maPlayer');
  function fmt(s){s=Math.round(s||0);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}
  function show(){document.getElementById('maraAudio').classList.add('on');}
  function get(u){return fetch(u+'?t='+Date.now(),{cache:'no-store'}).then(function(r){if(!r.ok)throw 0;return r.json();});}
  get('version.json').then(function(v){ if(!v.audio) return; src.brief=v.audio;
    document.getElementById('maBriefSub').textContent='· KW '+v.kw+(v.audio_sek?' · '+fmt(v.audio_sek):'');
    document.getElementById('maBrief').classList.add('on'); show(); }).catch(function(){});
  get('ansage.json').then(function(a){
    var heute=new Date().toISOString().slice(0,10);
    if(!a.mp3 || (a.gueltig_ab && heute<a.gueltig_ab) || (a.gueltig_bis && heute>a.gueltig_bis)) return;
    src.ansage=a.mp3;
    document.getElementById('maAnsLabel').innerHTML=(a.titel||'Ansage')+(a.von?' <span class="ma-sub">· '+a.von+'</span>':'');
    if(a.text){var t=document.getElementById('maAnsText');t.textContent='📣 '+a.text;t.classList.add('on');}
    document.getElementById('maAns').classList.add('on'); show(); }).catch(function(){});
  function icons(){document.getElementById('maBriefIco').textContent=(cur==='brief'&&!P.paused)?'❚❚':'▶';
    document.getElementById('maAnsIco').textContent=(cur==='ansage'&&!P.paused)?'❚❚':'📣';}
  window.maraPlay=function(k){ if(!src[k]) return;
    if(cur===k){ P.paused?P.play():P.pause(); }
    else { cur=k; P.src=src[k]; P.play(); document.getElementById('maProg').classList.add('on'); }
    icons(); };
  P.addEventListener('play',icons); P.addEventListener('pause',icons); P.addEventListener('ended',icons);
  P.addEventListener('timeupdate',function(){ if(P.duration) document.getElementById('maBar').style.width=(100*P.currentTime/P.duration)+'%'; });
  document.getElementById('maProg').addEventListener('click',function(e){ if(!P.duration) return; var r=this.getBoundingClientRect(); P.currentTime=P.duration*(e.clientX-r.left)/r.width; });
})();
</script>'''


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

    # Audio-Leiste (Wochen-Briefing + Platz für Kanzlei-Ansage)
    marker = "<!-- ══ TABS ══ -->"
    if marker not in html:
        fail("Einfügepunkt für die Audio-Leiste nicht gefunden.")
    html = html.replace(marker, AUDIO_BAR + "\n" + marker, 1)

    # Maschinenlesbare Kopie der Daten (für Dubletten-Abgleich nächste Woche)
    payload = json.dumps({"kw": kw, "monat": monat, "datum": datum,
                          "steuer": steuer["items"], "ki": ki["items"]},
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
    ap.add_argument("--audio", help="MP3 des Wochen-Briefings (optional, aus _radar/tts.py)")
    ap.add_argument("--dry-run", action="store_true", help="nur bauen und prüfen, nichts ablegen")
    a = ap.parse_args()

    if a.dump_previous:
        return dump_previous(a.kanzlei, a.dump_previous)
    if not (a.steuer and a.ki):
        fail("--steuer und --ki werden benötigt")

    steuer = json.load(open(a.steuer, encoding="utf-8"))
    ki = json.load(open(a.ki, encoding="utf-8"))
    problems = check_items(steuer, "Steuer", "steuer") + check_items(ki, "KI", "ki")
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
    audio_rel, audio_sek = None, None
    if a.audio:
        if not os.path.exists(a.audio) or os.path.getsize(a.audio) < 10000:
            fail(f"Audio-Datei fehlt oder ist leer: {a.audio}")
        os.makedirs(os.path.join(base, "audio"), exist_ok=True)
        audio_rel = f"audio/KW{kw:02d}-{year}.mp3"
        shutil.copyfile(a.audio, os.path.join(base, audio_rel))
        try:
            audio_sek = round(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", a.audio], capture_output=True, text=True).stdout.strip()))
        except Exception:
            audio_sek = None
    with open(os.path.join(base, "archiv", f"KW{kw:02d}-{year}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(base, "version.json"), "w", encoding="utf-8") as f:
        json.dump({"kw": kw, "jahr": int(year), "stand": datum, "monat": monat,
                   "steuer_items": len(steuer["items"]), "ki_items": len(ki["items"]),
                   "audio": audio_rel, "audio_sek": audio_sek,
                   "erstellt": datetime.now().isoformat(timespec="minutes")},
                  f, ensure_ascii=False, indent=1)
    print(f"✅ KW {kw}/{year} gebaut und geprüft: {a.kanzlei}/index.html + archiv/KW{kw:02d}-{year}.html")
    print(f"   Steuer-Items: {len(steuer['items'])} | KI-Items: {len(ki['items'])} | {len(html):,} Zeichen")


if __name__ == "__main__":
    main()
