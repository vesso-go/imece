"""ZIM paketlerinin iç yapısını döker (geliştirme aracı). Kullanım: python incele.py <imece klasörü> <zim>..."""
import collections, importlib.util, os, sys, time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
spec = importlib.util.spec_from_file_location("imece", os.path.join(sys.argv[1], "imece.py"))
imece = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imece)

for yol in sys.argv[2:]:
    z = imece.Zim(yol)
    print("=" * 70)
    print(os.path.basename(yol), "| sürüm %d.%d | girdi %d | küme %d" % (z.ana, z.alt, z.n, z.kume_n))
    print("mimeler:", z.mimeler)
    t0 = time.time()
    ns = collections.Counter()
    mime = collections.Counter()
    yon = 0
    ozel = []
    onek = collections.Counter()
    for i in range(z.n):
        g = z.giris(i)
        ns[g["ns"]] += 1
        if "yonlendirme" in g:
            yon += 1
        else:
            mime[(g["ns"], z.mime_adi(g))] += 1
        if g["ns"] in ("M", "X", "W"):
            ozel.append((g["ns"], g["url"], "->%d" % g["yonlendirme"] if "yonlendirme" in g else z.mime_adi(g)))
        if g["ns"] == "C" and ":" in g["url"][:25]:
            onek[g["url"].split(":", 1)[0]] += 1
    print("tarama %.1f sn | ad alanları: %s | yönlendirme: %d" % (time.time() - t0, dict(ns), yon))
    for k, v in sorted(mime.items(), key=lambda x: -x[1])[:12]:
        print("   ", k, v)
    print("özel girdiler:")
    for o in ozel:
        boy = ""
        if not o[2].startswith("->"):
            try:
                boy = len(z.icerik(z.giris(z.find(o[0], o[1]))))
            except Exception as e:
                boy = "hata %s" % e
        print("   ", o, boy)
    for ad in ("Counter", "Tags", "Scraper", "Source", "Name", "Flavour", "LongDescription"):
        i = z.find("M", ad)
        if i is not None:
            print("  M/%s = %s" % (ad, z.icerik(z.coz(i))[:300].decode("utf-8", "replace")))
    b, n = z.baslik_dizini()
    print("başlık dizini (ön makale) adedi:", n, "| ön ekler:", onek.most_common(12))
    for j in list(range(0, min(n, 8))) + list(range(max(0, n - 4), n)):
        g = z._baslik_giris(j)
        print("    %6d %s | %s | %s" % (j, g["ns"], g["baslik"], g["url"]))
    ana = z.ana_sayfa_url()
    if ana:
        ns_, _, u = ana.partition("/")
        h = z.icerik(z.coz(z.find(ns_, u)))
        print("ana sayfa:", ana, len(h), "bayt | bağlantı sayısı ~", h.count(b"<a "))
