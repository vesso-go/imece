"""Test sonuç dosyalarından (json) karşılaştırma tablosu üretir.
Kullanım: python tablo.py <test klasörü> [eski sürüm eki] [yeni sürüm eki]     (varsayılan: 07 08)
Beklenen dosyalar: sonuc-XX.json (senaryolar.py), arayuz-XX.json (arayuz.mjs), acilis-XX.json (acilis.py)."""
import json, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
d = sys.argv[1]
ESKI = sys.argv[2] if len(sys.argv) > 2 else "18"
YENI = sys.argv[3] if len(sys.argv) > 3 else "19"
ad_ = lambda ek: "0.%d" % int(ek)  # "09" → 0.9, "10" → 0.10


def oku(ad):
    try:
        return {s["kod"]: s for s in json.load(open(os.path.join(d, ad), encoding="utf-8"))["sonuc"]}
    except Exception:
        return {}


def temiz(t, n=230):
    t = re.sub(r"[A-Z]:\\[^ |;]+", "(yol)", str(t)).replace("\n", " ").replace("|", "/")
    t = re.sub(r"\s+", " ", t)
    return t if len(t) <= n else t[:n - 1] + "…"


for baslik, kok in (("Açılış senaryoları (Windows, PATH'te Python yok)", "acilis"), ("Sunucu ve içerik senaryoları", "sonuc"),
                    ("Arayüz senaryoları (gerçek Chrome)", "arayuz")):
    e, y = oku("%s-%s.json" % (kok, ESKI)), oku("%s-%s.json" % (kok, YENI))
    if not y:
        continue
    print("\n### %s\n" % baslik)
    print("| Kod | Senaryo | %s | %s | %s'deki kanıt |" % (ad_(ESKI), ad_(YENI), ad_(YENI)))
    print("|---|---|---|---|---|")
    for kod, s in y.items():
        print("| %s | %s | %s | %s | %s |" % (kod, temiz(s["ad"], 140), e[kod]["durum"] if kod in e else "yok", s["durum"], temiz(s["kanit"], 330)))
    for ad, v in ((ad_(ESKI), e), (ad_(YENI), y)):
        if not v:
            continue
        g = len([1 for s in v.values() if s["durum"] == "GEÇTİ"])
        k = len([1 for s in v.values() if s["durum"] == "KALDI"])
        print("\n%s: %d senaryo, %d geçti, %d kaldı%s" % (ad, len(v), g, k, ", %d atlandı" % (len(v) - g - k) if len(v) - g - k else ""), end="")
    print()
kalan = [(a, kod, s) for a in ("acilis", "sonuc", "arayuz") for kod, s in oku("%s-%s.json" % (a, YENI)).items() if s["durum"] == "KALDI"]
if kalan:
    print("\n### %s'de kalan senaryoların kanıtları\n" % ad_(YENI))
    for a, kod, s in kalan:
        print("- **%s** %s — %s" % (kod, temiz(s["ad"], 140), temiz(s["kanit"], 420)))
