"""Ölçek ölçümü: bir kitabın başlık dizinini sıfırdan kurar; süre, bellek ve sorgu hızını yazar.
Kullanım: python olcek.py <imece klasörü> <zim dosyası>"""
import importlib.util, os, sys, time, tracemalloc

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
spec = importlib.util.spec_from_file_location("imece", os.path.join(sys.argv[1], "imece.py"))
imece = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imece)

z = imece.Zim(sys.argv[2])
tracemalloc.start()
t0 = time.time()
d = imece.Dizin.kur(z)
sure = time.time() - t0
_, tepe = tracemalloc.get_traced_memory()
tracemalloc.stop()
print("%s: %d madde, %d başlık" % (os.path.basename(sys.argv[2]), len(d.mad), len(d.idx)))
print("dizin kurma: %.1f sn (bellek izleme açıkken; gerçekte daha hızlı), en yüksek ek bellek %.0f MB, kalıcı %.0f MB" % (
    sure, tepe / 1e6, (len(d.duz) + 4 * (len(d.idx) * 2 + len(d.mad))) / 1e6))
t0 = time.time()
d2 = imece.Dizin.kur(z)
print("dizin kurma (izleme kapalı): %.1f sn" % (time.time() - t0))
for s in ("atatürk", "savas", "istanbul universitesi", "zzzyokboylebirsey", "a", "ikinci dünya savaşı muharebeleri", "1923"):
    t0 = time.time()
    r = d.ara(z, s, 30)
    print("  ara %-36r %3d sonuç  %6.1f ms   %s" % (s, len(r), (time.time() - t0) * 1000, " | ".join(x["baslik"] for x in r[:3])))
t0 = time.time()
l, sonraki, toplam = d.liste(z, "K", 0, 200)
print("  K harfi ilk 200: %.1f ms, toplam %d; ilk: %s" % ((time.time() - t0) * 1000, toplam, ", ".join(x["baslik"] for x in l[:4])))
t0 = time.time()
l, sonraki, toplam = d.liste(z, "K", toplam - 150, 200)
print("  K harfi son sayfa: %.1f ms; son: %s" % ((time.time() - t0) * 1000, ", ".join(x["baslik"] for x in l[-3:])))
print("  kovalar: " + " ".join("%s:%d" % (h, d.kova[h][1] - d.kova[h][0]) for h in imece.HARFLER))
print("  bölümler: " + ", ".join("%s(%d)" % (b["ad"], b["adet"]) for b in d.bolum[:8]))
