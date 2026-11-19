"""Rehber metinlerinin kaynak ve onay kayıtlarını denetler.

Rehber metinleri `uygulama/index.html` içinde `<!--rehber:AD-->` … `<!--/rehber:AD-->` işaretleri arasında,
sesli karar ağaçları `uygulama/rehberler/*.js` dosyalarında durur. Her bölümün kaynakları ve (varsa) uzman onayı
`uygulama/rehber-kaynak.js` dosyasındadır. Onay, metnin o günkü hâlinin özetine (SHA-256) bağlıdır: metin
değişirse onay kendiliğinden geçersiz sayılır ve bölüm yeniden "onay bekliyor" görünür.

Kullanım:
  python rehber_onay.py <imece klasörü> ozet      her bölümün şu anki özetini yazar (onay kaydına bu yazılır)
  python rehber_onay.py <imece klasörü> denetle   kayıtların tutarlılığını denetler; sorun varsa 1 ile çıkar
  (ikisine de --json eklenirse çıktı JSON olur)
"""
import hashlib, json, os, re, sys


def oku(kok):
    uyg = os.path.join(kok, "uygulama")
    ham = open(os.path.join(uyg, "rehber-kaynak.js"), encoding="utf-8").read()
    m = re.search(r"window\.REHBER_KAYNAK\s*=\s*(\{.*\})\s*;?\s*$", ham, re.S)
    if not m:
        raise SystemExit("rehber-kaynak.js beklenen biçimde değil (window.REHBER_KAYNAK = {…};)")
    veri = json.loads(m.group(1))
    sayfa = open(os.path.join(uyg, "index.html"), "rb").read()
    return uyg, veri, sayfa


def bolum_metni(uyg, sayfa, ad, b):
    """Bölümün özeti alınacak ham baytları; bulunamazsa None."""
    if b.get("dosya"):
        yol = os.path.join(uyg, b["dosya"])
        return open(yol, "rb").read() if os.path.exists(yol) else None
    m = re.search(("<!--rehber:%s-->(.*?)<!--/rehber:%s-->" % (ad, ad)).encode(), sayfa, re.S)
    return m.group(1) if m else None


def incele(kok):
    uyg, veri, sayfa = oku(kok)
    sorun, bolumler = [], {}
    sayfa_metin = sayfa.decode("utf-8")
    for ad, b in veri.get("bolumler", {}).items():
        ham = bolum_metni(uyg, sayfa, ad, b)
        ozet = hashlib.sha256(ham).hexdigest() if ham is not None else None
        kayit = {"ozet": ozet, "durum": b.get("durum"), "kaynak": len(b.get("kaynaklar") or []), "onay": "yok"}
        bolumler[ad] = kayit
        if ham is None:
            sorun.append("%s: metni bulunamadı (işaretler ya da dosya eksik)" % ad)
            continue
        if b.get("durum") not in ("taslak", "kaynakli"):
            sorun.append("%s: durum 'taslak' ya da 'kaynakli' olmalı" % ad)
        nolar = set()
        for k in b.get("kaynaklar") or []:
            eksik = [a for a in ("no", "kurum", "baslik", "adres", "erisim") if not k.get(a)]
            if eksik:
                sorun.append("%s: kaynak %s için eksik alan: %s" % (ad, k.get("no"), ", ".join(eksik)))
            if k.get("no") in nolar:
                sorun.append("%s: kaynak numarası yineleniyor: %s" % (ad, k.get("no")))
            nolar.add(k.get("no"))
            if k.get("adres") and not re.match(r"^https?://[^\s]+$", k["adres"]):
                sorun.append("%s: kaynak %s adresi geçersiz" % (ad, k.get("no")))
            if k.get("erisim") and not re.match(r"^\d{4}-\d{2}-\d{2}$", k["erisim"]):
                sorun.append("%s: kaynak %s erişim tarihi YYYY-AA-GG olmalı" % (ad, k.get("no")))
        if b.get("durum") == "kaynakli":
            if not nolar:
                sorun.append("%s: 'kaynakli' deniyor ama kaynak yok" % ad)
            if not b.get("gozden") or not re.match(r"^\d{4}-\d{2}-\d{2}$", b.get("gozden", "")):
                sorun.append("%s: gözden geçirme tarihi yok" % ad)
        if b.get("dosya"):
            # sesli karar ağacı: her düğümün "kn" alanı kaynak numaralarını taşır
            m = re.search(r"window\.REHBER\s*=\s*(\{.*\})\s*;?\s*$", ham.decode("utf-8"), re.S)
            try:
                dugumler = json.loads(m.group(1))["dugumler"]
            except Exception:
                dugumler = None
                sorun.append("%s: rehber dosyası okunamadı (window.REHBER = {…}; bekleniyor)" % ad)
            if dugumler is not None:
                atif = set()
                for kimlik, d in dugumler.items():
                    kn = d.get("kn") or []
                    if not all(isinstance(n, int) for n in kn):
                        sorun.append("%s: %s düğümünde kaynak işareti sayı değil" % (ad, kimlik))
                        continue
                    atif.update(kn)
                    if b.get("durum") == "kaynakli" and not kn and not d.get("kaynaksiz"):
                        sorun.append("%s: kaynağa bağlanmamış düğüm: %s" % (ad, kimlik))
                for n in sorted(atif - nolar):
                    sorun.append("%s: metinde [%d] numaralı kaynağa atıf var ama kaynak listede yok" % (ad, n))
                for n in sorted(nolar - atif):
                    sorun.append("%s: [%s] numaralı kaynak listede var ama metinde hiçbir yere bağlanmamış" % (ad, n))
        else:
            govde = ham.decode("utf-8")
            atif = set()
            for m in re.finditer(r'data-kn="([^"]*)"', govde):
                for n in m.group(1).split(","):
                    if n.strip().isdigit():
                        atif.add(int(n))
                    else:
                        sorun.append("%s: kaynak işareti sayı değil: %r" % (ad, m.group(1)))
            for n in sorted(atif - nolar):
                sorun.append("%s: metinde [%d] numaralı kaynağa atıf var ama kaynak listede yok" % (ad, n))
            for n in sorted(nolar - atif):
                sorun.append("%s: [%s] numaralı kaynak listede var ama metinde hiçbir yere bağlanmamış" % (ad, n))
            if b.get("durum") == "kaynakli":
                # kaynaklı bir bölümde her kutu (kart) en az bir kaynağa bağlanmalı
                for kart in re.split(r'<div class="kart"', govde)[1:]:
                    if "data-kn=" not in kart and "data-kaynaksiz" not in kart:
                        baslik = re.search(r"<h3>(.*?)</h3>", kart)
                        sorun.append("%s: kaynağa bağlanmamış kutu: %s" % (ad, baslik.group(1) if baslik else kart[:40]))
        o = b.get("onay")
        if o:
            eksik = [a for a in ("ad", "unvan", "tarih", "ozet") if not o.get(a)]
            if eksik:
                sorun.append("%s: onay kaydında eksik alan: %s" % (ad, ", ".join(eksik)))
            kayit["onay"] = "gecerli" if o.get("ozet") == ozet else "gecersiz"
            if kayit["onay"] == "gecersiz":
                sorun.append("%s: metin onaylandığı hâlinden farklı (onay geçersiz; yeniden onay gerekir)" % ad)
            if b.get("durum") != "kaynakli":
                sorun.append("%s: kaynaksız (taslak) bir bölüm onaylı olamaz" % ad)
    for ad in re.findall(r"<!--rehber:([a-z0-9_-]+)-->", sayfa_metin):
        if ad not in veri.get("bolumler", {}):
            sorun.append("%s: sayfada işaretli ama rehber-kaynak.js içinde kaydı yok" % ad)
    return bolumler, sorun


if __name__ == "__main__":
    kok = sys.argv[1]
    komut = sys.argv[2] if len(sys.argv) > 2 else "denetle"
    bolumler, sorun = incele(kok)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if "--json" in sys.argv:
        print(json.dumps({"bolumler": bolumler, "sorun": sorun}, ensure_ascii=False))
    elif komut == "ozet":
        for ad, k in bolumler.items():
            print("%-10s %s" % (ad, k["ozet"]))
    else:
        for ad, k in bolumler.items():
            print("%-10s durum: %-9s kaynak: %2d  onay: %s" % (ad, k["durum"], k["kaynak"], k["onay"]))
        print("\n".join("SORUN: " + s for s in sorun) if sorun else "Sorun yok.")
    sys.exit(1 if sorun and komut == "denetle" else 0)
