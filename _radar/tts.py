#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MARA Radar – Sprachausgabe (Text → MP3) mit Piper (offline, Open Source)

Aufruf:
    python3 _radar/tts.py --text sprechtext.txt --out briefing.mp3 [--stimme kerstin]

Stimmen (deutsch):
    kerstin   – weiblich (de_DE-kerstin-low, Lizenz CC0)
    thorsten  – männlich (de_DE-thorsten-high, Lizenz CC0)

Beim ersten Aufruf wird `piper-tts` installiert und das Stimmenmodell von
huggingface.co/rhasspy/piper-voices geladen (Cache: ~/.cache/mara-tts).
"""
import argparse, os, subprocess, sys, urllib.request

STIMMEN = {
    "kerstin":  "de/de_DE/kerstin/low/de_DE-kerstin-low",
    "thorsten": "de/de_DE/thorsten/high/de_DE-thorsten-high",
}
BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
CACHE = os.path.expanduser("~/.cache/mara-tts")


def ensure_piper():
    try:
        import piper  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "piper-tts"], check=True)


def ensure_voice(name):
    os.makedirs(CACHE, exist_ok=True)
    rel = STIMMEN[name]
    model = os.path.join(CACHE, os.path.basename(rel) + ".onnx")
    for ext in (".onnx", ".onnx.json"):
        dst = model if ext == ".onnx" else model + ".json"
        if not os.path.exists(dst) or os.path.getsize(dst) < 1000:
            print(f"⬇️  Lade Stimme {name} ({ext}) …")
            urllib.request.urlretrieve(BASE + rel + ext, dst)
    return model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stimme", default="thorsten", choices=sorted(STIMMEN))
    a = ap.parse_args()

    text = open(a.text, encoding="utf-8").read().strip()
    if len(text) < 50:
        sys.exit("❌ Sprechtext fehlt oder ist zu kurz.")
    ensure_piper()
    model = ensure_voice(a.stimme)
    wav = a.out.rsplit(".", 1)[0] + ".wav"
    with open(a.text, "rb") as fin:
        subprocess.run([sys.executable, "-m", "piper", "-m", model, "-f", wav, "--sentence-silence", "0.35"],
                       stdin=fin, check=True, stderr=subprocess.DEVNULL)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-b:a", "64k", a.out], check=True)
    os.remove(wav)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.out],
                         capture_output=True, text=True).stdout.strip()
    print(f"✅ Audio erzeugt: {a.out} ({float(dur):.0f} s, Stimme {a.stimme})")


if __name__ == "__main__":
    main()
