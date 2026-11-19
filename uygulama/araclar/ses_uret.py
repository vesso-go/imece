#!/usr/bin/env python3
"""İmece — sesli rehber üretici.

uygulama/rehberler/*.js içindeki her düğümün "ses" metnini internetsiz çalışan
Türkçe sentetik sesle WAV dosyasına çevirir: uygulama/ses/<rehber>/<düğüm>.wav
Portal önce bu dosyaları çalar; yoksa cihazın kendi Türkçe sesine düşer.

Bir kez internet gerekir (ses motoru ve Türkçe ses modeli iner), sonra tamamen çevrimdışı.
  pip install piper-tts
  python ses_uret.py
"""
import json, os, re, subprocess, sys, urllib.request

UYG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KOK = os.path.dirname(UYG)
SES_DIR = os.path.join(KOK, "veri", "ses-modeli")
MODEL = "tr_TR-dfki-medium"
URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/"


def model_hazirla():
    os.makedirs(SES_DIR, exist_ok=True)
    for uz in (".onnx", ".onnx.json"):
        yol = os.path.join(SES_DIR, MODEL + uz)
        if not os.path.exists(yol):
            print(f"Ses modeli indiriliyor: {MODEL}{uz}")
            urllib.request.urlretrieve(URL + MODEL + uz, yol)
    return os.path.join(SES_DIR, MODEL + ".onnx")


def rehber_oku(yol):
    t = open(yol, encoding="utf-8").read()
    t = re.sub(r"^\s*//.*$", "", t, flags=re.M)
    t = t[t.index("{"): t.rindex("}") + 1]
    return json.loads(t)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    model = model_hazirla()
    rdir = os.path.join(UYG, "rehberler")
    for ad in sorted(os.listdir(rdir)):
        if not ad.endswith(".js"):
            continue
        r = rehber_oku(os.path.join(rdir, ad))
        hedef = os.path.join(UYG, "ses", r["id"])
        os.makedirs(hedef, exist_ok=True)
        for did, d in r["dugumler"].items():
            metin = d.get("ses") or d.get("metin")
            cikti = os.path.join(hedef, did + ".wav")
            print(f" ♪ {r['id']}/{did}")
            subprocess.run([sys.executable, "-m", "piper", "-m", model, "-f", cikti],
                           input=metin.encode("utf-8"), check=True)
    print("Bitti. Sesler uygulama/ses/ klasöründe.")


if __name__ == "__main__":
    main()
