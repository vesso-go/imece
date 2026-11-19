"""İmece test senaryoları. Çalışan bir İmece sunucusunu dışarıdan sınar.

Kullanım:  python senaryolar.py <imece klasörü> [--port 8642] [--indirme] [--json çıktı.json]

Doğruluk ölçüsü olarak uygulamanın kendi okuyucusu DEĞİL, bu dosyadaki bağımsız küçük
ZIM okuyucu kullanılır: "pakette gerçekte hangi maddeler var" sorusunun cevabı buradan gelir.
"""
import argparse, http.client, json, lzma, os, re, socket, struct, subprocess, sys, tempfile, time, urllib.parse, wave

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ap = argparse.ArgumentParser()
ap.add_argument("klasor")
ap.add_argument("--port", type=int, default=8642)
ap.add_argument("--indirme", action="store_true", help="İnternet isteyen indirme senaryolarını da çalıştır")
ap.add_argument("--buyuk", action="store_true", help="600 MB'tan büyük kitapları da madde madde say")
ap.add_argument("--sadece", help="Yalnızca kodu bu harf(ler)le başlayan senaryoları çalıştır (ör. T ya da T,C)")
ap.add_argument("--json")
A = ap.parse_args()
HOST, PORT = "127.0.0.1", A.port
SONUC = []


# ---------------------------------------------------------------- HTTP
def istek(yol, yontem="GET", govde=None, basliklar=None, host=HOST, port=None, zaman=120):
    c = http.client.HTTPConnection(host, port or PORT, timeout=zaman)
    b = dict(basliklar or {})
    veri = None
    if govde is not None:
        veri = json.dumps(govde).encode("utf-8")
        b.setdefault("Content-Type", "application/json")
    c.request(yontem, yol, body=veri, headers=b)
    r = c.getresponse()
    icerik = r.read()
    c.close()
    return r.status, dict((k.lower(), v) for k, v in r.getheaders()), icerik


def js(yol, **kw):
    kod, b, ic = istek(yol, **kw)
    try:
        return kod, json.loads(ic.decode("utf-8"))
    except Exception:
        return kod, None


def q(s):
    return urllib.parse.quote(s, safe="")


def yolq(s):
    return "/".join(urllib.parse.quote(p, safe="") for p in s.split("/"))


# ---------------------------------------------------------------- bağımsız ZIM okuyucu
try:
    from compression import zstd as _z

    def zstd_ac(b):
        return _z.decompress(b)
except Exception:
    zstd_ac = None


class Z:
    def __init__(self, yol):
        self.f = open(yol, "rb")
        h = self.f.read(80)
        self.n, self.kn, self.up, self.tp, self.kp, self.mp, self.ana, _, self.cp = struct.unpack_from("<IIQQQQIIQ", h, 24)
        self.f.seek(self.mp)
        self.mime = [x.decode() for x in self.f.read(self.up - self.mp).split(b"\0\0")[0].split(b"\0")]
        self.f.seek(self.up)
        self.ptr = struct.unpack("<%dQ" % self.n, self.f.read(8 * self.n))

    def g(self, i):
        self.f.seek(self.ptr[i])
        ham = self.f.read(4096)
        m, _, ns = struct.unpack_from("<HBc", ham, 0)
        bas = 12 if m == 0xFFFF else 16
        s1 = ham.index(b"\0", bas)
        s2 = ham.index(b"\0", s1 + 1)
        url = ham[bas:s1].decode("utf-8", "replace")
        d = {"ns": ns.decode("latin-1"), "url": url, "baslik": ham[s1 + 1:s2].decode("utf-8", "replace") or url, "mime": m}
        if m == 0xFFFF:
            d["yon"] = struct.unpack_from("<I", ham, 8)[0]
        else:
            d["kume"], d["blob"] = struct.unpack_from("<II", ham, 8)
        return d

    def bul(self, ns, url):
        lo, hi = 0, self.n
        while lo < hi:
            o = (lo + hi) // 2
            g = self.g(o)
            if (g["ns"], g["url"]) < (ns, url):
                lo = o + 1
            else:
                hi = o
        if lo < self.n:
            g = self.g(lo)
            if (g["ns"], g["url"]) == (ns, url):
                return lo
        return None

    def icerik(self, g):
        self.f.seek(self.kp + 8 * g["kume"])
        bas = struct.unpack("<Q", self.f.read(8))[0]
        son = struct.unpack("<Q", self.f.read(8))[0] if g["kume"] + 1 < self.kn else self.cp
        self.f.seek(bas)
        ham = self.f.read(son - bas)
        sik, genis = ham[0] & 15, ham[0] & 16
        v = ham[1:]
        if sik == 4:
            v = lzma.LZMADecompressor().decompress(v)
        elif sik == 5:
            v = zstd_ac(v)
        fmt, os_ = ("<Q", 8) if genis else ("<I", 4)
        a = struct.unpack_from(fmt, v, os_ * g["blob"])[0]
        b = struct.unpack_from(fmt, v, os_ * (g["blob"] + 1))[0]
        return v[a:b]

    def maddeler(self):
        """Ön makaleler: {url: başlık} (yönlendirme olmayanlar) ve yönlendirme başlıkları."""
        i = self.bul("X", "listing/titleOrdered/v1")
        if i is None:
            return None, None
        b = self.icerik(self.g(i))
        mad, yon = {}, {}
        for j in struct.unpack("<%dI" % (len(b) // 4), b):
            g = self.g(j)
            (yon if "yon" in g else mad)[g["url"]] = g["baslik"]
        return mad, yon


# ---------------------------------------------------------------- Türkçe sıra anahtarı (bağımsız)
# Beklenen sıra: baştaki işaretler sayılmaz; harfler Türk alfabesi sırasıyla (ç c'den, ı i'den önce/sonra
# yerinde); alfabede olmayan aksanlı harfler yalın harf gibi (é = e); işaret < rakam < harf.
import unicodedata
_ALF = "abcçdefgğhıijklmnoöpqrsştuüvwxyz"


def tr_kucuk(s):
    s = s.replace("I", "ı").replace("İ", "i").lower()
    return "".join(c if c in _ALF or not unicodedata.normalize("NFD", c)[0].isascii() or not c.isalpha()
                   else unicodedata.normalize("NFD", c)[0] for c in s)


def tr_anahtar(s):
    t = tr_kucuk(s).lstrip(" \t\"'‘’“”«»‹›([{<-–—.,:;!?¿¡*#/\\_~`´^&%$+=|@")
    return [(2, _ALF.index(c)) if c in _ALF else ((1, ord(c)) if c.isdigit() else ((0, ord(c)) if ord(c) < 128 else (3, ord(c)))) for c in t]


# ---------------------------------------------------------------- çatı
def senaryo(kod, ad):
    def sar(f):
        if A.sadece and not kod.startswith(tuple(A.sadece.split(","))):
            return f
        t0 = time.time()
        try:
            durum, kanit = f()
        except Exception as e:
            durum, kanit = "KALDI", "beklenmeyen hata: %s: %s" % (type(e).__name__, e)
        SONUC.append({"kod": kod, "ad": ad, "durum": durum, "kanit": kanit, "sure": round(time.time() - t0, 1)})
        print("%-4s %-8s %s\n       %s" % (kod, durum, ad, kanit))
        return f
    return sar


def sonuc(kosul, kanit):
    return ("GEÇTİ" if kosul else "KALDI"), kanit


_, DURUM = js("/api/durum")
SURUM = DURUM["surum"]
VERI = DURUM["veri"]
_, KITAPLAR = js("/api/kitaplar")
YENI = js("/api/kitap?k=" + q(KITAPLAR[0]["id"]))[0] == 200 if KITAPLAR else False
KITAP_SAYISI = len(KITAPLAR)
# Çok büyük kitaplar (ör. 700.000 maddelik tam Vikipedi) tek tek madde sayan senaryolara ancak --buyuk ile girer:
# 0.6'nın A–Z'si böyle bir kitabı baştan sona dolaşmayı saatlerce sürdürüyor.
if not A.buyuk:
    BUYUKLER = [k["baslik"] for k in KITAPLAR if k["boyut_mb"] > 600]
    KITAPLAR = [k for k in KITAPLAR if k["boyut_mb"] <= 600]
    if BUYUKLER:
        print("(büyük kitaplar bu koşuda hariç: %s)" % ", ".join(BUYUKLER))
print("İmece %s | %d kitap | veri: %s | kitap giriş ucu: %s\n" % (SURUM, len(KITAPLAR), VERI, "var" if YENI else "yok"))


def zim_yolu(kid):
    for d in os.listdir(os.path.join(VERI, "zim")):
        if d.endswith(".zim") and re.sub(r"[^a-zA-Z0-9_.-]", "_", os.path.splitext(d)[0]) == kid:
            return os.path.join(VERI, "zim", d)


GERCEK = {}


def gercek(kid):
    if kid not in GERCEK:
        GERCEK[kid] = Z(zim_yolu(kid)).maddeler()
    return GERCEK[kid]


def kitap_bul(parca):
    for k in KITAPLAR:
        if parca in k["id"]:
            return k["id"]


def harf_listesi(kid):
    """Kitabın A–Z kovaları: 0.7'de /api/kitap'tan, 0.6'da sabit 29 harf."""
    if YENI:
        return [h["harf"] for h in js("/api/kitap?k=" + q(kid))[1]["harfler"] if h["adet"]]
    return "A B C Ç D E F G Ğ H I İ J K L M N O Ö P R S Ş T U Ü V Y Z".split()


def dizin_tumu(kid, harf, sinir=10 ** 9):
    """Bir harfin bütün sayfalarını dolaşır."""
    out, n = [], 0
    if YENI:
        bas = 0
        while bas is not None and len(out) < sinir:
            kod, r = js("/api/dizin?k=%s&harf=%s&bas=%d&adet=500" % (q(kid), q(harf), bas))
            out += r["liste"]
            bas = r.get("sonraki")
            n += 1
    else:
        s = 0
        while len(out) < sinir:
            kod, r = js("/api/dizin?k=%s&harf=%s&sayfa=%d" % (q(kid), q(harf), s))
            out += r["liste"]
            n += 1
            if not r.get("devam"):
                break
            s += 1
    return out, n


# ================================================================ A. AÇILIŞ
@senaryo("A1", "Kök adres uygulamayı açar")
def _():
    kod, b, _ic = istek("/")
    k2, b2, ic2 = istek(b.get("location", "/x"))
    return sonuc(kod == 302 and k2 == 200 and "İmece" in ic2.decode("utf-8"), "/ → %s → %d, %d bayt" % (b.get("location"), k2, len(ic2)))


@senaryo("A2", "Durum ucu: sürüm, zstd desteği, boş alan")
def _():
    return sonuc(DURUM["zstd"] and DURUM["bos_mb"] > 0, "sürüm %s, zstd=%s, boş %d MB" % (SURUM, DURUM["zstd"], DURUM["bos_mb"]))


@senaryo("A3", "Arayüz dosyaları internete bağımlı değil (dış kaynak yok)")
def _():
    bulunan = []
    for kok, _d, ds in os.walk(os.path.join(A.klasor, "uygulama")):
        for d in ds:
            if d.endswith((".html", ".js", ".css")):
                t = open(os.path.join(kok, d), encoding="utf-8").read()
                for m in re.finditer(r"""(?:src|href)\s*=\s*["'](https?:)?//[^"']+|@import\s+url|url\(\s*["']?https?:""", t):
                    bulunan.append(d + ": " + m.group(0)[:60])
    return sonuc(not bulunan, "dış kaynak yok" if not bulunan else "; ".join(bulunan[:5]))


# ================================================================ C. KÜTÜPHANE
@senaryo("C1", "Kitap listesi: başlık, dil, tarih, boyut dolu")
def _():
    eksik = [k["id"] for k in KITAPLAR if not (k["baslik"] and k["dil"] and k["tarih"] and k["boyut_mb"])]
    return sonuc(len(KITAPLAR) >= 3 and not eksik, "%d kitap: %s" % (len(KITAPLAR), ", ".join(k["baslik"] for k in KITAPLAR)))


@senaryo("C2", "Her kitabın paket ana sayfası açılıyor")
def _():
    out = []
    for k in KITAPLAR:
        kod, b, _ic = istek("/zim/%s/" % q(k["id"]))
        k2, b2, ic = istek(b.get("location", "/x"))
        out.append((k["id"][:22], kod, k2, len(ic)))
    return sonuc(all(o[1] == 302 and o[2] == 200 and o[3] > 500 for o in out), str(out))


@senaryo("C3", "Madde sayfası ve içindeki stil/betik/resim dosyaları eksiksiz geliyor")
def _():
    toplam, kotu = 0, []
    for k in KITAPLAR:
        mad, _y = gercek(k["id"])
        for url in list(mad)[:: max(1, len(mad) // 4)][:4]:
            taban = "/zim/%s/C/%s" % (q(k["id"]), yolq(url))
            kod, b, ic = istek(taban)
            if kod != 200:
                kotu.append("%s → %d" % (url, kod))
                continue
            for m in set(re.findall(r"""(?:src|href)="([^"#:?]+\.(?:css|js|png|svg|webp|jpg|gif))["?]""", ic.decode("utf-8", "replace"))):
                hedef = urllib.parse.urljoin("http://x" + taban, m)[8:]
                toplam += 1
                kk = istek(hedef)[0]
                if kk != 200:
                    kotu.append("%s içindeki %s → %d" % (url, m, kk))
    return sonuc(toplam > 20 and not kotu, "%d kaynak dosyası denendi; hatalı: %s" % (toplam, kotu[:4] or "yok"))


@senaryo("C4", "Yönlendirme başlığı asıl maddeye götürüyor")
def _():
    k = kitap_bul("wikibooks") or kitap_bul("wikiquote") or KITAPLAR[0]["id"]
    _m, yon = gercek(k)
    if not yon:
        return "ATLANDI", "Bu kitapta yönlendirme başlığı yok."
    url = next(iter(yon))
    kod, b, _ic = istek("/zim/%s/C/%s" % (q(k), yolq(url)))
    k2 = istek(b.get("location", "/x"))[0]
    return sonuc(kod == 302 and k2 == 200, "%s → %s (%d)" % (url, urllib.parse.unquote(b.get("location", "")), k2))


@senaryo("C5", "Pakette olmayan sayfa anlaşılır biçimde 404 dönüyor")
def _():
    kod, b, ic = istek("/zim/%s/C/Boyle_bir_madde_yok_12345" % q(KITAPLAR[0]["id"]))
    return sonuc(kod == 404 and "yok" in ic.decode("utf-8"), "%d: %s" % (kod, ic.decode("utf-8")[:60]))


@senaryo("C6", "Başlık araması Türkçe büyük/küçük harfe takılmıyor (istanbul, ISI, ATATÜRK, şiir)")
def _():
    out, tamam = [], True
    for s, bekle in (("istanbul", "İstanbul"), ("ısı", "Isı"), ("ISI", "Isı"), ("ATATÜRK", "Atatürk"), ("şiir", "Şiir"), ("ŞİİR", "Şiir")):
        r = js("/api/ara?q=" + q(s))[1] or []
        var = any(x["baslik"].startswith(bekle) for x in r)
        tamam &= var
        out.append("%s:%s" % (s, "var" if var else "YOK"))
    return sonuc(tamam, " ".join(out))


@senaryo("C7", "Arama, başlığın ortasındaki kelimeyi de buluyor")
def _():
    k = kitap_bul("chemistry") or KITAPLAR[0]["id"]
    mad, _y = gercek(k)
    aday = [b for b in mad.values() if b.count(" ") == 1 and len(b.split()[1]) > 6 and b.split()[1].isalpha()][:6]
    out, n = [], 0
    for b in aday:
        kel = b.split()[1]
        r = js("/api/ara?k=%s&adet=300&q=%s" % (q(k), q(kel)))[1] or []
        var = any(b in (x["baslik"], x.get("hedef")) for x in r)
        n += var
        out.append("%s→%s" % (kel, "buldu" if var else "BULAMADI"))
    return sonuc(aday and n == len(aday), "aranan ikinci kelimeler: " + ", ".join(out))


@senaryo("C8", "Türkçe karaktersiz yazınca da buluyor (isi→Isı, siir→Şiir, celik→Çelik)")
def _():
    out, tamam = [], True
    for s, bekle in (("isi", "Isı"), ("siir", "Şiir"), ("celik", "Çelik"), ("ataturk", "Atatürk")):
        r = js("/api/ara?q=" + q(s))[1] or []
        var = any(x["baslik"].startswith(bekle) for x in r)
        tamam &= var
        out.append("%s:%s" % (s, "var" if var else "YOK"))
    return sonuc(tamam, " ".join(out))


@senaryo("C9", "Kitaba özel arama sadece o kitaptan sonuç getiriyor")
def _():
    k = kitap_bul("wikiquote") or KITAPLAR[0]["id"]
    r = js("/api/ara?k=%s&q=a" % q(k))[1] or []
    return sonuc(r and all(x["kitap"] == k for x in r), "%d sonuç, hepsi %s" % (len(r), k[:20]))


# ================================================================ K. KİTAP GİRİŞ EKRANI
@senaryo("K1", "Kitap giriş verisi var: madde sayısı, harfler, künye")
def _():
    if not YENI:
        return "KALDI", "Bu sürümde kitap giriş ucu yok; kitap açılınca paketin kendi ana sayfası geliyor."
    out, tamam = [], True
    for k in KITAPLAR:
        r = js("/api/kitap?k=" + q(k["id"]))[1]
        tamam &= bool(r.get("madde") and r.get("harfler") and r.get("baslik") and r.get("ana"))
        out.append("%s: %s madde, %d harf kovası, %d bölüm" % (r.get("baslik"), r.get("madde"), len([h for h in r["harfler"] if h["adet"]]), len(r.get("bolumler") or [])))
    return sonuc(tamam, " | ".join(out))


@senaryo("K2", "Gösterilen madde sayısı pakettekiyle birebir aynı")
def _():
    if not YENI:
        return "KALDI", "Bu sürüm madde sayısını hiç göstermiyor."
    out, tamam = [], True
    for k in KITAPLAR:
        mad, _y = gercek(k["id"])
        r = js("/api/kitap?k=" + q(k["id"]))[1]
        tamam &= r["madde"] == len(mad)
        out.append("%s: gösterilen %s / gerçek %d" % (k["id"][:18], r["madde"], len(mad)))
    return sonuc(tamam, " | ".join(out))


@senaryo("K3", "ASIL SORUN: paket ana sayfasından kaç maddeye ulaşılıyor, bizim ekrandan kaç maddeye?")
def _():
    out, tamam = [], True
    for k in KITAPLAR:
        mad, yon = gercek(k["id"])
        kod, b, _ic = istek("/zim/%s/" % q(k["id"]))
        ic = istek(b["location"])[2].decode("utf-8", "replace")
        bag = set(urllib.parse.unquote(h).split("#")[0].lstrip("./") for h in re.findall(r'href="([^"]+)"', ic))
        ana_ulasan = len([u for u in bag if u in mad or u in yon])
        ulasan = set()
        for h in harf_listesi(k["id"]):
            ulasan.update(x["yol"].split("/", 1)[1] for x in dizin_tumu(k["id"], h)[0])
        eksik = [u for u in mad if u not in ulasan]
        tamam &= not eksik
        out.append("%s: %d madde; paket ana sayfası %d maddeye bağlı; A–Z'den ulaşılan %d, ULAŞILAMAYAN %d%s" % (
            k["id"][:18], len(mad), ana_ulasan, len(mad) - len(eksik), len(eksik), (" (örn. %s)" % ", ".join(mad[u] for u in eksik[:4])) if eksik else ""))
    return sonuc(tamam, "\n       ".join(out))


@senaryo("K4", "A–Z sayfalaması tutarlı: tekrar yok, atlama yok")
def _():
    k = kitap_bul("wikiquote") or KITAPLAR[0]["id"]
    h = "A"
    l, n = dizin_tumu(k, h)
    yollar = [x["yol"] for x in l]
    return sonuc(len(l) > 100 and len(set(yollar)) == len(yollar), "%s harfi: %d başlık, %d istek, tekrar eden %d" % (h, len(l), n, len(yollar) - len(set(yollar))))


@senaryo("K5", "A–Z listesi Türk alfabesine göre sıralı (ç, ğ, ı, ö, ş, ü yerinde)")
def _():
    k = kitap_bul("wikiquote") or KITAPLAR[0]["id"]
    out, tamam = [], True
    for h in ("A", "S", "C"):
        l = [x["baslik"] for x in dizin_tumu(k, h)[0]]
        bozuk = [(a, b) for a, b in zip(l, l[1:]) if tr_anahtar(a) > tr_anahtar(b)]
        tamam &= not bozuk and len(l) > 20
        out.append("%s: %d başlık, sırası bozuk %d çift%s" % (h, len(l), len(bozuk), (" (örn. '%s' > '%s')" % bozuk[0]) if bozuk else ""))
    return sonuc(tamam, " | ".join(out))


@senaryo("K6", "Rastgele madde: her seferinde geçerli ve farklı maddeler")
def _():
    k = KITAPLAR[0]["id"]
    yollar, kotu = set(), 0
    for _i in range(15):
        r = js("/api/rastgele?k=" + q(k))[1]
        yollar.add(r["yol"])
        kotu += istek("/zim/%s/%s" % (q(k), yolq(r["yol"])))[0] != 200
    return sonuc(len(yollar) >= 8 and not kotu, "15 denemede %d farklı madde, açılmayan %d" % (len(yollar), kotu))


@senaryo("K7", "Bölümler: Vikikitap'ta 'Yemek' bölümü kendi maddelerini listeliyor")
def _():
    if not YENI:
        return "KALDI", "Bu sürümde bölüm/kategori yok."
    k = kitap_bul("wikibooks")
    r = js("/api/kitap?k=" + q(k))[1]
    b = [x for x in r.get("bolumler") or [] if x["ad"].startswith("Yemek")]
    if not b:
        return "KALDI", "Yemek bölümü yok; bölümler: %s" % [x["ad"] for x in (r.get("bolumler") or [])[:8]]
    l, bas = [], 0
    while bas is not None:
        rr = js("/api/bolum?k=%s&ad=%s&bas=%d&adet=500" % (q(k), q(b[0]["anahtar"]), bas))[1]
        l += rr["liste"]
        bas = rr.get("sonraki")
    mad, _y = gercek(k)
    beklenen = len([t for t in mad.values() if t.startswith("Yemek:")])
    return sonuc(len(l) == beklenen == b[0]["adet"] and all(x["baslik"].startswith("Yemek:") for x in l),
                 "bölüm sayacı %d, listelenen %d, pakette gerçekte %d" % (b[0]["adet"], len(l), beklenen))


@senaryo("K8", "Büyük kitap (50.000 madde): giriş ekranı ve arama hızlı")
def _():
    k = kitap_bul("wikipedia_tr_top")
    if not k:
        return "ATLANDI", "50.000 maddelik paket kurulu değil."
    t0 = time.time()
    if YENI:
        for _i in range(120):
            r = js("/api/kitap?k=" + q(k))[1]
            if r["dizin"]["durum"] != "hazirlaniyor":
                break
            time.sleep(1)
        hazir = time.time() - t0
        t1 = time.time()
        r = js("/api/kitap?k=" + q(k))[1]
        giris = time.time() - t1
    t2 = time.time()
    a = js("/api/ara?k=%s&q=%s" % (q(k), q("savaş")))[1]
    ara = time.time() - t2
    t3 = time.time()
    l, n = dizin_tumu(k, "M", sinir=500)
    liste = time.time() - t3
    if not YENI:
        return sonuc(ara < 1 and liste < 3, "arama %.2f sn (%d sonuç), M harfi ilk 500: %.2f sn; giriş ekranı yok" % (ara, len(a), liste))
    return sonuc(giris < 0.5 and ara < 0.5 and liste < 1, "dizin %s (%.1f sn bekledi), giriş verisi %.2f sn, 'savaş' araması %.2f sn (%d sonuç), M harfi ilk 500: %.2f sn; %s madde" % (
        r["dizin"]["durum"], hazir, giris, ara, len(a), liste, r["madde"]))


# ================================================================ G. GÜVENLİK
@senaryo("G1", "Uygulama klasörünün dışındaki dosyalar okunamıyor")
def _():
    out = []
    for y in ("/uygulama/../imece.py", "/uygulama/..%2fimece.py", "/uygulama/%2e%2e/imece.py", "/uygulama/..\\imece.py",
              "/veri/muzik/../durum.json", "/veri/muzik/..%5cdurum.json", "/uygulama/....//imece.py"):
        out.append((y, istek(y)[0]))
    return sonuc(all(k != 200 for _y, k in out), ", ".join("%s→%d" % o for o in out))


@senaryo("G2", "Başka bir sitenin sayfası İmece'ye komut gönderemiyor (yabancı Origin)")
def _():
    kod = istek("/api/durdur", "POST", {}, {"Origin": "http://kotu.example"})[0]
    return sonuc(kod == 403, "yabancı Origin ile POST → %d" % kod)


@senaryo("G3", "Alan adı oyunuyla (DNS rebinding) komut gönderilemiyor")
def _():
    kod = istek("/api/durdur", "POST", {}, {"Origin": "http://kotu.example:%d" % PORT, "Host": "kotu.example:%d" % PORT})[0]
    return sonuc(kod == 403, "Host ve Origin 'kotu.example' iken POST → %d (200 ise saldırı başarılı)" % kod)


@senaryo("G4", "Kitap sayfasındaki betikler İmece'nin yönetim uçlarına ulaşamıyor")
def _():
    k = KITAPLAR[0]["id"]
    kod, b, _ic = istek("/zim/%s/" % q(k))
    b2 = istek(b["location"])[1]
    csp = b2.get("content-security-policy", "")
    yalitik = "sandbox" in csp and "allow-same-origin" not in csp
    kimliksiz = istek("/api/durdur", "POST", {}, {"Origin": "null"})[0]
    return sonuc(yalitik and kimliksiz == 403, "kitap sayfası güvenlik başlığı: %s; yalıtılmış sayfadan gelen POST → %d" % (
        csp[:60] or "YOK (kitap içindeki betik arayüze ve /api/ayar, /api/flash uçlarına erişebilir)", kimliksiz))


@senaryo("G5", "Ağ modunda (kutu) yönetim uçları sadece kutunun kendisinden kullanılabiliyor")
def _():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = None
    finally:
        s.close()
    if not ip or ip.startswith("127."):
        return "ATLANDI", "Bu bilgisayarın yerel ağ adresi yok."
    gecici = tempfile.mkdtemp(prefix="imece-ag-")
    import shutil
    hedef = os.path.join(gecici, "imece")
    shutil.copytree(A.klasor, hedef, ignore=shutil.ignore_patterns("veri", "ayarlar.json", "__pycache__"))
    p = subprocess.Popen([sys.executable, os.path.join(hedef, "imece.py"), "--ag", "--port", str(PORT + 1), "--tarayici-acma"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _i in range(40):
            try:
                if istek("/api/durum", host=ip, port=PORT + 1, zaman=2)[0] == 200:
                    break
            except Exception:
                time.sleep(0.25)
        oku = istek("/api/kitaplar", host=ip, port=PORT + 1)[0]
        yaz = istek("/api/ayar", "POST", {"veri": os.path.join(gecici, "ele-gecirildi")}, host=ip, port=PORT + 1)[0]
        dur = js("/api/durum", host=ip, port=PORT + 1)[1]
        olustu = os.path.exists(os.path.join(gecici, "ele-gecirildi"))
        yerel = istek("/api/durdur", "POST", {}, port=PORT + 1)[0]
    finally:
        p.terminate()
        p.wait(10)
        shutil.rmtree(gecici, ignore_errors=True)
    return sonuc(oku == 200 and yaz == 403 and not olustu and yerel == 200,
                 "ağdaki cihazdan (%s): okuma %d, veri klasörünü değiştirme %d%s; kutunun kendisinden yönetim %d; ağdaki cihaza klasör yolu %s" % (
                     ip, oku, yaz, " — KLASÖR OLUŞTU" if olustu else "", yerel, "GÖSTERİLİYOR" if os.sep in str(dur.get("veri", "")) else "gösterilmiyor"))


# ================================================================ M. MÜZİK
@senaryo("M1", "Müzik: dosya listede, parça ortasından (Range) okuma doğru")
def _():
    md = os.path.join(VERI, "muzik", "test")
    os.makedirs(md, exist_ok=True)
    yol = os.path.join(md, "İmece deneme sesi.wav")
    with wave.open(yol, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(bytes(range(256)) * 250)
    try:
        l = js("/api/muzik")[1]
        ad = [m for m in l if "deneme" in m]
        kod, b, ic = istek("/veri/muzik/" + yolq(ad[0]), basliklar={"Range": "bytes=1000-1999"})
        asil = open(yol, "rb").read()
        return sonuc(kod == 206 and ic == asil[1000:2000] and b.get("content-range") == "bytes 1000-1999/%d" % len(asil),
                     "listede: %s; Range → %d, %s, %d bayt" % (ad[0], kod, b.get("content-range"), len(ic)))
    finally:
        os.remove(yol)
        os.rmdir(md)


# ================================================================ T. TAM METİN ARAMA
# Doğruluk ölçüsü yine bağımsız: kitap bu dosyadaki okuyucuyla açılır, sayfalar Python'un HTML
# ayrıştırıcısıyla (uygulamanın kullandığı yöntemden farklı) yazıya çevrilir ve kelimeler burada sayılır.
import html.parser
TM_VAR = bool(DURUM.get("tam_metin"))
_TM_T = {ord(a): b for a, b in zip("IİıçÇğĞöÖşŞüÜ", "iiiccggoossuu")}


def b_sade(s):
    out = []
    for ch in s.translate(_TM_T):
        if ch >= "À" and ch < "ɐ":
            t = unicodedata.normalize("NFD", ch)[0]
            if t.isascii() and t.isalpha():
                ch = t
        out.append(ch)
    return "".join(out).lower()


class _Yazi(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.p, self.gizli, self.govde = [], 0, False

    def handle_starttag(self, t, a):
        if t == "body":
            self.govde = True
        if t in ("script", "style", "noscript", "template"):
            self.gizli += 1

    def handle_endtag(self, t):
        if t in ("script", "style", "noscript", "template") and self.gizli:
            self.gizli -= 1

    def handle_data(self, d):
        if self.govde and not self.gizli:
            self.p.append(d)


YUMUSAMA_VAR = tuple(int(x) for x in SURUM.split(".")[:2]) >= (0, 15)


def b_govde(w):
    """Ünsüz yumuşaması kuralının bu betikteki bağımsız yazımı: yumuşamış gövde ya da None."""
    if len(w) < 4 or not w.isascii() or w[-1] not in "ptk":
        return None
    if sum(c in "aeiou" for c in w) < 2 and not w.endswith("nk"):
        return None
    return w[:-1] + {"p": "b", "t": "d", "k": "g"}[w[-1]]


def b_uyar(tok, w):
    """Dizindeki tok kelimesi, aranan w ile eşleşmeli mi? Ön ek; 0.15'ten beri ünsüz yumuşaması da ("kitap" → "kitabı")."""
    if tok.startswith(w):
        return True
    g = b_govde(w) if YUMUSAMA_VAR else None
    return bool(g) and len(tok) > len(g) and tok.startswith(g) and tok[len(g)] in "aeiou"


def b_kelimeler(metin):
    return re.findall(r"[^\W_]+", b_sade(metin))


TM_GERCEK = {}


def tm_gercek(kid):
    """{url: (başlık kelimeleri, yazı kelimeleri)}: kitabın bütün maddeleri, bağımsız okunup kelimelere ayrılmış."""
    if kid not in TM_GERCEK:
        z = Z(zim_yolu(kid))
        mad, _yon = z.maddeler()
        girdi = sorted((z.g(z.bul("C", u)) for u in mad), key=lambda g: (g["kume"], g["blob"]))
        out, son_kume, son_veri = {}, None, None
        for g in girdi:
            if "html" not in z.mime[g["mime"]]:
                continue
            p = _Yazi()
            p.feed(z.icerik(g).decode("utf-8", "replace"))
            p.close()
            out[g["url"]] = (b_kelimeler(g["baslik"]), b_kelimeler(" ".join(p.p)))
        TM_GERCEK[kid] = out
    return TM_GERCEK[kid]


def tm_tumu(kid, sorgu, sinir=3000):
    """Bir sorgunun bütün sonuç sayfalarını dolaşır: (yollar, ilk sayfa)."""
    yollar, ilk, bas = [], None, 0
    while len(yollar) < sinir:
        kod, r = js("/api/metin-ara?k=%s&adet=100&bas=%d&q=%s" % (q(kid), bas, q(sorgu)))
        if ilk is None:
            ilk = r
        yollar += [x["yol"].split("/", 1)[1] for x in r["sonuc"]]  # baştaki ad alanı ("C/") atılır
        bas += len(r["sonuc"])
        if not r["devam"] or not r["sonuc"]:
            break
    return yollar, ilk


def tm_bekle(kidler, sn):
    son = time.time() + sn
    while True:
        d = {k["id"]: k.get("tam_metin") for k in js("/api/kitaplar")[1]}
        eksik = [k for k in kidler if d.get(k) != "hazir"]
        if not eksik or time.time() > son:
            return eksik, d
        time.sleep(2)


TM_KUCUK = kitap_bul("wikibooks") or (KITAPLAR[0]["id"] if KITAPLAR else None)


@senaryo("T1", "Tam metin dizinleri arka planda kendiliğinden kuruluyor; her kitabın bütün maddeleri dizine giriyor")
def _():
    if not TM_VAR:
        return sonuc(False, "bu sürümde tam metin arama yok (/api/durum içinde tam_metin alanı yok)")
    eksik, d = tm_bekle([k["id"] for k in KITAPLAR], 3600 if A.buyuk else 900)
    ozet = js("/api/durum")[1]["tam_metin"]
    fark = []
    for k in KITAPLAR:
        o = js("/api/kitap?k=" + q(k["id"]))[1]
        if o["tam_metin"].get("durum") == "hazir" and o["tam_metin"].get("madde") != o["madde"]:
            fark.append("%s: kitapta %d, dizinde %s" % (k["id"][:28], o["madde"], o["tam_metin"].get("madde")))
    return sonuc(not eksik and not fark, "%d kitabın %d tanesinin dizini hazır (%s); dizinler toplam %s MB; madde sayısı tutmayan: %s" % (
        len(KITAPLAR), len(KITAPLAR) - len(eksik), "eksik: " + ", ".join("%s=%s" % (x[:24], d.get(x)) for x in eksik) if eksik else "eksik yok",
        ozet["boyut_mb"], fark or "yok"))


@senaryo("T2", "Yazının içinde geçen kelime: sonuç kümesi, kitabı bağımsız okuyup kelime kelime sayınca çıkanla birebir aynı")
def _():
    if not TM_VAR:
        return sonuc(False, "tam metin arama yok")
    g = tm_gercek(TM_KUCUK)
    sayac = {}
    for u, (bk, yk) in g.items():
        for w in set(bk) | set(yk):
            if len(w) >= 5 and w.isascii() and w.isalpha():
                sayac[w] = sayac.get(w, 0) + 1
    aday = sorted(w for w, n in sayac.items() if 3 <= n <= 80)
    secilen = aday[::max(1, len(aday) // 14)][:14]
    hata, toplam = [], 0
    for w in secilen:
        beklenen = {u for u, (bk, yk) in g.items() if any(b_uyar(x, w) for x in bk) or any(b_uyar(x, w) for x in yk)}
        gelen, _ilk = tm_tumu(TM_KUCUK, w)
        toplam += len(beklenen)
        if set(gelen) != beklenen or len(gelen) != len(set(gelen)):
            hata.append("%s: beklenen %d, gelen %d, eksik %s, fazla %s" % (w, len(beklenen), len(gelen), sorted(beklenen - set(gelen))[:2], sorted(set(gelen) - beklenen)[:2]))
    return sonuc(secilen and not hata, "%s (%d madde): %d kelime denendi (%s…), toplam %d eşleşme; tutmayan: %s" % (
        TM_KUCUK[:24], len(g), len(secilen), ", ".join(secilen[:6]), toplam, hata[:3] or "yok"))


@senaryo("T3", "Türkçe harfler ve büyük/küçük harf: 'ISI', 'ısı', 'isi' aynı sonucu veriyor; 'dunya savasi' = 'Dünya Savaşı'")
def _():
    if not TM_VAR:
        return sonuc(False, "tam metin arama yok")
    kid = kitap_bul("wikipedia_tr_top") or TM_KUCUK
    out, tamam = [], True
    for grup in (("ISI", "ısı", "isi", "Isı"), ("dunya savasi", "Dünya Savaşı", "DÜNYA SAVAŞI"), ("şiir", "siir", "ŞİİR"), ("çağ", "cag", "ÇAĞ")):
        r = [[x["yol"] for x in js("/api/metin-ara?k=%s&adet=50&q=%s" % (q(kid), q(s)))[1]["sonuc"]] for s in grup]
        ayni = all(x == r[0] for x in r) and len(r[0]) > 0
        tamam = tamam and ayni
        out.append("%s → %d sonuç, hepsi aynı: %s" % (" = ".join(grup), len(r[0]), ayni))
    return sonuc(tamam, "; ".join(out))


@senaryo("T4", "Tırnak içindeki söz öbeği: yalnızca kelimelerin o sırayla yan yana geçtiği maddeler geliyor")
def _():
    if not TM_VAR:
        return sonuc(False, "tam metin arama yok")
    g = tm_gercek(TM_KUCUK)
    ikili = {}
    for u, (bk, yk) in g.items():
        gor = set()
        for kel in (bk, yk):
            for a, b in zip(kel, kel[1:]):
                if len(a) >= 5 and len(b) >= 5 and a.isascii() and b.isascii() and a.isalpha() and b.isalpha():
                    gor.add((a, b))
        for c in gor:
            ikili[c] = ikili.get(c, 0) + 1
    out, hata, n = [], [], 0
    for (a, b), adet in sorted(ikili.items()):
        if not 2 <= adet <= 40:
            continue
        obek = {u for u, (bk, yk) in g.items() if any(x == a and y == b for kel in (bk, yk) for x, y in zip(kel, kel[1:]))}
        ikisi = {u for u, (bk, yk) in g.items() if any(b_uyar(x, a) for x in bk + yk) and any(b_uyar(x, b) for x in bk + yk)}
        if len(ikisi) < len(obek) + 3:
            continue  # ayırt edici değil: iki kelime zaten hep yan yana geçiyor
        gelen = set(tm_tumu(TM_KUCUK, '"%s %s"' % (a, b))[0])
        serbest = set(tm_tumu(TM_KUCUK, "%s %s" % (a, b))[0])
        n += 1
        out.append('"%s %s": öbek %d, ikisi de geçen %d' % (a, b, len(gelen), len(serbest)))
        if gelen != obek or serbest != ikisi:
            hata.append('"%s %s": öbek beklenen %d gelen %d; serbest beklenen %d gelen %d' % (a, b, len(obek), len(gelen), len(ikisi), len(serbest)))
        if n >= 8:
            break
    return sonuc(n >= 3 and not hata, "%d söz öbeği denendi (%s); tutmayan: %s" % (n, "; ".join(out[:3]), hata[:2] or "yok"))


@senaryo("T5", "Özet: aranan kelimenin geçtiği yer gösteriliyor ve vurgulanan parça gerçekten o kelime")
def _():
    if not TM_VAR:
        return sonuc(False, "tam metin arama yok")
    kid = kitap_bul("wikipedia_tr_top") or TM_KUCUK
    toplam = vurgulu = 0
    yanlis, ornek = [], ""
    for s in ("peroksit", "dünya savaşı", "fotosentez", "Osmanlı donanması", "ısı yalıtımı", '"birinci dünya savaşı"'):
        kel = b_kelimeler(s)
        for x in js("/api/metin-ara?k=%s&adet=20&q=%s" % (q(kid), q(s)))[1]["sonuc"]:
            toplam += 1
            if x["vurgu"]:
                vurgulu += 1
            for a, b in x["vurgu"]:
                parca = b_sade(x["ozet"][a:b])
                if not any(b_uyar(parca, k) for k in kel):
                    yanlis.append("%s → “%s”" % (s, x["ozet"][a:b]))
            if not ornek and len(x["vurgu"]) >= 2 and s == "dünya savaşı":
                a, b = x["vurgu"][0]
                ornek = "%s: …%s[%s]%s…" % (x["baslik"], x["ozet"][max(0, a - 25):a], x["ozet"][a:b], x["ozet"][b:b + 25])
    return sonuc(toplam >= 40 and not yanlis and vurgulu >= toplam * 0.9, "%d sonucun %d tanesinde vurgu var; yanlış yere düşen vurgu: %s; örnek: %s" % (
        toplam, vurgulu, yanlis[:3] or "yok", ornek))


@senaryo("T6", "Sıralama: adı aranan sözle aynı olan madde en üstte geliyor")
def _():
    if not TM_VAR:
        return sonuc(False, "tam metin arama yok")
    kid = kitap_bul("wikipedia_tr_top") or TM_KUCUK
    mad, _yon = gercek(kid)
    adlar = sorted(t for t in mad.values() if 2 <= len(t.split()) <= 3 and all(len(w) >= 5 and w.isalpha() for w in t.split()))
    secilen = adlar[::max(1, len(adlar) // 25)][:25]
    ilk = uc = 0
    kotu = []
    for t in secilen:
        r = [x["baslik"] for x in js("/api/metin-ara?k=%s&adet=10&q=%s" % (q(kid), q(t)))[1]["sonuc"]]
        ilk += r[:1] == [t]
        uc += t in r[:3]
        if t not in r[:3]:
            kotu.append("%s → %s" % (t, r[:2]))
    return sonuc(secilen and uc == len(secilen) and ilk >= len(secilen) * 0.8, "%d madde adı arandı: %d tanesinde o madde ilk sırada, %d tanesinde ilk üçte; ilk üçe giremeyen: %s" % (
        len(secilen), ilk, uc, kotu[:3] or "yok"))


@senaryo("T7", "Adında geçmeyip yalnızca yazısında geçen kelime: ad araması bulamıyor, tam metin arama buluyor")
def _():
    if not TM_VAR:
        return sonuc(False, "tam metin arama yok")
    g = tm_gercek(TM_KUCUK)
    adlarda = set()
    for bk, _yk in g.values():
        adlarda.update(bk)
    _mad, yon = gercek(TM_KUCUK)
    for t in (yon or {}).values():
        adlarda.update(b_kelimeler(t))
    sayac = {}
    for bk, yk in g.values():
        for w in set(yk):
            if len(w) >= 7 and w.isascii() and w.isalpha():
                sayac[w] = sayac.get(w, 0) + 1
    aday = sorted(w for w, n in sayac.items() if 2 <= n <= 20 and not any(a.startswith(w) or w in a for a in adlarda))
    secilen = aday[::max(1, len(aday) // 10)][:10]
    out, tamam = [], bool(secilen)
    for w in secilen:
        ad = js("/api/ara?k=%s&adet=50&q=%s" % (q(TM_KUCUK), q(w)))[1]
        tm = tm_tumu(TM_KUCUK, w)[0]
        tamam = tamam and not ad and len(tm) >= 2
        out.append("%s: adında %d, yazısında %d" % (w, len(ad), len(tm)))
    return sonuc(tamam, "%d kelime denendi; %s" % (len(secilen), "; ".join(out[:5])))


TM_ORNEK = {}


def _tm_ornek_kur():
    """Ayrı bir İmece kopyası (geçici klasör, kendi veri klasörü, 50.000 maddelik kitabın kopyası)."""
    import shutil
    kid = kitap_bul("wikipedia_tr_top")
    if not kid:
        return None
    kok = tempfile.mkdtemp(prefix="imece-tm-")
    shutil.copy(os.path.join(A.klasor, "imece.py"), kok)
    shutil.copytree(os.path.join(A.klasor, "uygulama"), os.path.join(kok, "uygulama"))
    os.makedirs(os.path.join(kok, "veri", "zim"))
    shutil.copy(zim_yolu(kid), os.path.join(kok, "veri", "zim"))
    TM_ORNEK.update(kok=kok, kid=kid, port=PORT + 3, p=None)
    return TM_ORNEK


def _tm_ornek_baslat():
    o = TM_ORNEK
    o["p"] = subprocess.Popen([sys.executable, os.path.join(o["kok"], "imece.py"), "--port", str(o["port"]), "--tarayici-acma"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _i in range(80):
        try:
            if istek("/api/durum", port=o["port"], zaman=2)[0] == 200:
                return True
        except Exception:
            time.sleep(0.25)
    return False


def _tm_ornek_durum():
    return js("/api/kitap?k=" + q(TM_ORNEK["kid"]), port=TM_ORNEK["port"])[1]["tam_metin"]


def _sure_olc(port, kid, n=8):
    """Bir ad araması ve bir kitap girişi isteğinin ortanca süresi (ms)."""
    s = []
    for i in range(n):
        t = time.perf_counter()
        js("/api/ara?k=%s&q=%s" % (q(kid), q(("ankara", "deniz", "savaş", "kimya")[i % 4])), port=port)
        js("/api/dizin?k=%s&harf=K&bas=0&adet=200" % q(kid), port=port)
        s.append((time.perf_counter() - t) * 1000)
    return sorted(s)[len(s) // 2]


@senaryo("T12", "Türkçe ünsüz yumuşaması: \"kitap\" yazınca \"kitabı\", \"çocuk\" yazınca \"çocuğu\" geçen maddeler de bulunuyor; tek heceli kelimeler genişletilmiyor")
def _():
    if not TM_VAR:
        return sonuc(False, "tam metin arama yok")
    if not YUMUSAMA_VAR:
        return sonuc(False, "bu sürümde ünsüz yumuşaması yok: \"kitap\" araması \"kitabı\" geçen maddeleri bulmuyor")
    g = tm_gercek(TM_KUCUK)
    import bisect
    ters = {}  # kelime -> o kelimenin geçtiği maddeler
    for u, (bk, yk) in g.items():
        for x in set(bk) | set(yk):
            ters.setdefault(x, set()).add(u)
    sirali = sorted(ters)

    def onek(p):  # p ile başlayan bir kelimesi olan maddeler
        out, i = set(), bisect.bisect_left(sirali, p)
        while i < len(sirali) and sirali[i].startswith(p):
            out |= ters[sirali[i]]
            i += 1
        return out
    aday = []
    for w in sirali:
        gv = b_govde(w)
        if not gv or len(w) < 5 or not w.isalpha():
            continue
        duz_ = onek(w)
        genis = set(duz_)
        for unlu in "aeiou":
            genis |= onek(gv + unlu)
        if len(genis) > len(duz_) and len(genis) <= 300:
            aday.append((w, duz_, genis))
    secilen = aday[::max(1, len(aday) // 10)][:10]
    hata, ornek = [], []
    for w, duz_, genis in secilen:
        gelen = set(tm_tumu(TM_KUCUK, w)[0])
        ornek.append("%s: %d → %d madde" % (w, len(duz_), len(genis)))
        if gelen != genis:
            hata.append("%s: beklenen %d, gelen %d" % (w, len(genis), len(gelen)))
    tek = []
    for w in ("kart", "saat", "sert", "halk"):  # tek heceli ya da uzun ünlülü: gövdesi değişmez, genişletilmemeli
        duz_ = onek(w)
        gelen = set(tm_tumu(TM_KUCUK, w)[0])
        if w != "saat" and gelen != duz_:
            hata.append("%s genişletilmiş: %d ≠ %d" % (w, len(gelen), len(duz_)))
        tek.append("%s %d" % (w, len(gelen)))
    return sonuc(len(secilen) >= 3 and not hata, "%d kelime denendi (yumuşamış biçimi kitapta geçenlerden): %s; tutmayan: %s; denetim kelimeleri: %s" % (
        len(secilen), "; ".join(ornek[:6]), hata[:3] or "yok", ", ".join(tek)))


@senaryo("T8", "Kurulum yarıda kesilince (İmece aniden kapanınca) kaldığı yerden sürüyor; sonuçlar kesintisiz kurulanla aynı")
def _():
    if not TM_VAR:
        return sonuc(False, "tam metin arama yok")
    o = _tm_ornek_kur()
    if not o or not _tm_ornek_baslat():
        return sonuc(False, "deneme kopyası başlatılamadı")
    son, st = time.time() + 180, {}
    while time.time() < son:
        st = _tm_ornek_durum()
        if st.get("durum") == "hazirlaniyor" and st.get("yuzde", 0) >= 30:
            break
        time.sleep(0.5)
    o["kurarken_ms"] = _sure_olc(o["port"], o["kid"])
    kesilen = _tm_ornek_durum().get("yuzde", 0)
    o["p"].kill()  # aniden: kapatma düğmesi değil, sürecin öldürülmesi
    o["p"].wait(10)
    if not _tm_ornek_baslat():
        return sonuc(False, "kesintiden sonra yeniden açılmadı")
    ilk_gorulen, son = None, time.time() + 300
    while time.time() < son:
        st = _tm_ornek_durum()
        if st.get("durum") == "hazirlaniyor" and ilk_gorulen is None:
            ilk_gorulen = st.get("yuzde", 0)
        if st.get("durum") == "hazir":
            break
        time.sleep(0.5)
    o["bosta_ms"] = _sure_olc(o["port"], o["kid"])
    asil = js("/api/kitap?k=" + q(o["kid"]))[1]
    farkli = []
    for s in ("peroksit", "dünya savaşı", "fotosentez", '"osmanlı imparatorluğu"', "ve"):
        a = [x["yol"] for x in js("/api/metin-ara?k=%s&adet=100&q=%s" % (q(o["kid"]), q(s)))[1]["sonuc"]]
        b = [x["yol"] for x in js("/api/metin-ara?k=%s&adet=100&q=%s" % (q(o["kid"]), q(s)), port=o["port"])[1]["sonuc"]]
        if a != b:
            farkli.append("%s (%d / %d)" % (s, len(a), len(b)))
    tamam = (st.get("durum") == "hazir" and ilk_gorulen is not None and ilk_gorulen >= kesilen - 3 and kesilen >= 30
             and st.get("madde") == asil["madde"] and not farkli)
    return sonuc(tamam, "%%%d'de süreç öldürüldü; yeniden açılınca %%%s'den sürdü; bitince dizinde %s madde (kitapta %d); 5 sorgunun sonuçları kesintisiz kurulan dizinle aynı: %s" % (
        kesilen, ilk_gorulen, st.get("madde"), asil["madde"], "evet" if not farkli else "HAYIR: %s" % farkli))


@senaryo("T9", "Dizin kurulurken uygulama yanıt vermeyi sürdürüyor")
def _():
    o = TM_ORNEK
    if "kurarken_ms" not in o:
        return sonuc(False, "ölçülemedi (T8 çalışmadı)")
    return sonuc(o["kurarken_ms"] < 1500, "ad araması + harf listesi isteği, ortanca: dizin kurulurken %.0f ms, boştayken %.0f ms" % (o["kurarken_ms"], o["bosta_ms"]))


@senaryo("T10", "Ayarlar: 'Dizinleri sil' yer açıyor ve aramayı ad aramasına indiriyor; yeniden açınca dizin baştan kuruluyor")
def _():
    import shutil
    o = TM_ORNEK
    if not o.get("p"):
        return sonuc(False, "deneme kopyası yok (T8 çalışmadı)")
    try:
        port, kid = o["port"], o["kid"]
        dosya = os.path.join(o["kok"], "veri", "dizin", kid + ".imt")
        once = os.path.getsize(dosya) if os.path.exists(dosya) else 0
        kod, r = js("/api/tam-metin-sil", yontem="POST", govde={}, port=port)
        silindi = not os.path.exists(dosya)
        m = js("/api/metin-ara?k=%s&q=peroksit" % q(kid), port=port)[1]
        ad = js("/api/ara?k=%s&q=peroksit" % q(kid), port=port)[1]
        time.sleep(4)  # kapalıyken kendiliğinden yeniden kurulmamalı
        kapali_kaldi = not os.path.exists(dosya + ".yarim") and _tm_ornek_durum().get("durum") == "kapali"
        js("/api/ayar", yontem="POST", govde={"tam_metin": True}, port=port)
        yeniden, son = {}, time.time() + 60
        while time.time() < son:
            yeniden = _tm_ornek_durum()
            if yeniden.get("durum") == "hazirlaniyor" and yeniden.get("yuzde", 0) >= 3:
                break
            time.sleep(0.5)
        tamam = (kod == 200 and once > 0 and silindi and abs(r["silinen_mb"] - once / 2 ** 20) < 1 and not m["sonuc"] and m["bekleyen"]
                 and m["bekleyen"][0]["durum"] == "kapali" and len(ad) > 0 and kapali_kaldi and yeniden.get("durum") == "hazirlaniyor")
        return sonuc(tamam, "silinen %.1f MB (dosya %.1f MB), dosya gitti: %s; tam metin sonuç %d (durum: %s), ad araması hâlâ %d sonuç; kapalıyken kendiliğinden kurulmadı: %s; açınca: %s %%%s" % (
            r["silinen_mb"], once / 2 ** 20, silindi, len(m["sonuc"]), m["bekleyen"][0]["durum"] if m["bekleyen"] else "-", len(ad), kapali_kaldi,
            yeniden.get("durum"), yeniden.get("yuzde")))
    finally:
        try:
            istek("/api/kapat", "POST", {}, port=o["port"], zaman=5)
            o["p"].wait(15)
        except Exception:
            o["p"].kill()
        shutil.rmtree(o["kok"], ignore_errors=True)


@senaryo("T11", "Ölçek: en büyük kitapta tam metin arama süreleri")
def _():
    if not TM_VAR:
        return sonuc(False, "tam metin arama yok")
    k = max(KITAPLAR, key=lambda x: x["madde"])
    o = js("/api/kitap?k=" + q(k["id"]))[1]
    if o["tam_metin"].get("durum") != "hazir":
        return sonuc(False, "%s: dizin hazır değil (%s)" % (k["baslik"], o["tam_metin"]))
    out, en_uzun = [], 0
    for s in ("fotosentez", "istanbul boğazı", '"birinci dünya savaşı"', "deprem fay hattı", "osmanlı", "ve", "bir"):
        t = time.perf_counter()
        r = js("/api/metin-ara?k=%s&adet=20&q=%s" % (q(k["id"]), q(s)))[1]
        ms = (time.perf_counter() - t) * 1000
        en_uzun = max(en_uzun, ms)
        out.append("%s: %.0f ms (%d sonuç%s)" % (s, ms, len(r["sonuc"]), "+" if r["devam"] else ""))
    return sonuc(en_uzun < 8000, "%s: %d madde, dizin %s MB (kitap %d MB) | %s" % (k["baslik"], o["madde"], o["tam_metin"].get("boyut_mb"), o["boyut_mb"], "; ".join(out)))


# ================================================================ E. KİTAP EKLEME VE SİLME
# Ayrı bir İmece kopyasında (geçici klasör, boş kütüphane) koşulur: asıl kütüphaneye dokunulmaz.
import hashlib
EK = {}
EK_VAR = istek("/api/kitap-ekle-denetle", "POST", {})[0] != 404
EK_YOK = "bu sürümde uygulamadan kitap ekleme/silme yok"


def _ek_kur():
    import shutil
    kok = tempfile.mkdtemp(prefix="imece-ekle-")
    shutil.copy(os.path.join(A.klasor, "imece.py"), kok)
    shutil.copytree(os.path.join(A.klasor, "uygulama"), os.path.join(kok, "uygulama"))
    EK.update(kok=kok, port=PORT + 4, zdir=os.path.join(kok, "veri", "zim"), ddir=os.path.join(kok, "veri", "dizin"),
              gecici=tempfile.mkdtemp(prefix="imece-ekle-kaynak-"))
    EK["p"] = subprocess.Popen([sys.executable, os.path.join(kok, "imece.py"), "--port", str(EK["port"]), "--tarayici-acma"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _i in range(80):
        try:
            if istek("/api/durum", port=EK["port"], zaman=2)[0] == 200:
                return True
        except Exception:
            time.sleep(0.25)
    return False


def ek_js(yol, **kw):
    return js(yol, port=EK["port"], **kw)


def ek_dosyalar():
    return sorted(os.listdir(EK["zdir"]))


def ek_kitaplar():
    return {k["id"]: k for k in ek_js("/api/kitaplar")[1]}


def ek_denetle(yol_ya_da_bas, ad, boy=None, **kw):
    if isinstance(yol_ya_da_bas, bytes):
        bas = yol_ya_da_bas
    else:
        with open(yol_ya_da_bas, "rb") as f:
            bas = f.read(80)
        boy = os.path.getsize(yol_ya_da_bas) if boy is None else boy
    return ek_js("/api/kitap-ekle-denetle", yontem="POST", govde={"ad": ad, "boy": boy, "bas": bas.hex()}, **kw)


def ek_gonder(veri, ad, basliklar=None):
    """Dosyayı (yol ya da bayt) /api/kitap-ekle ucuna gönderir. (kod, json); bağlantı koparsa (0, None)."""
    c = http.client.HTTPConnection(HOST, EK["port"], timeout=900)
    govde = veri if isinstance(veri, bytes) else open(veri, "rb")
    boy = len(veri) if isinstance(veri, bytes) else os.path.getsize(veri)
    try:
        c.request("POST", "/api/kitap-ekle?ad=" + q(ad), body=govde,
                  headers={"Content-Length": str(boy), "Content-Type": "application/octet-stream", **(basliklar or {})})
        r = c.getresponse()
        ic = r.read()
        try:
            return r.status, json.loads(ic.decode("utf-8"))
        except Exception:
            return r.status, None
    except OSError:
        return 0, None
    finally:
        if not isinstance(veri, bytes):
            govde.close()
        c.close()


def sha(yol):
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for p in iter(lambda: f.read(1 << 20), b""):
            h.update(p)
    return h.hexdigest()


EK_KUCUK, EK_IKINCI, EK_ORTA = kitap_bul("wikibooks"), kitap_bul("chemistry_nopic"), kitap_bul("computer_nopic")


@senaryo("E1", "Kütüphanedeki her kitap dosyası kendi içindeki sağlamayı tutuyor (ekleme denetiminin dayandığı kural gerçek paketlerde geçerli)")
def _():
    kotu, n, mb = [], 0, 0
    for k in KITAPLAR:
        yol = zim_yolu(k["id"])
        boy = os.path.getsize(yol)
        h = hashlib.md5()
        with open(yol, "rb") as f:
            bas = f.read(80)
            f.seek(0)
            kalan = boy - 16
            while kalan > 0:
                p = f.read(min(1 << 20, kalan))
                h.update(p)
                kalan -= len(p)
            son = f.read(16)
        n += 1
        mb += boy >> 20
        if struct.unpack_from("<Q", bas, 72)[0] != boy - 16 or h.digest() != son:
            kotu.append(k["id"])
    return sonuc(n > 0 and not kotu, "%d kitap (%d MB) denetlendi: sağlama yeri dosyanın son 16 baytı ve MD5 tutuyor; tutmayan: %s" % (n, mb, kotu or "yok"))


@senaryo("E2", "Dosyadan kitap ekleme: dosya bire bir kopyalanıyor, kitap kütüphaneye giriyor, dizinleri kuruluyor, madde açılıyor")
def _():
    if not EK_VAR:
        return sonuc(False, EK_YOK)
    if not _ek_kur():
        return sonuc(False, "deneme kopyası başlatılamadı")
    kaynak = zim_yolu(EK_KUCUK)
    on = ek_denetle(kaynak, os.path.basename(kaynak))
    kod, r = ek_gonder(kaynak, os.path.basename(kaynak))
    if kod != 200:
        return sonuc(False, "ön denetim %s; ekleme yanıtı %s %s" % (on, kod, r))
    hedef = os.path.join(EK["zdir"], os.path.basename(kaynak))
    ayni = os.path.exists(hedef) and sha(hedef) == sha(kaynak)
    asil = js("/api/kitap?k=" + q(EK_KUCUK))[1]
    o, son = {}, time.time() + 120
    while time.time() < son:
        o = ek_js("/api/kitap?k=" + q(r["id"]))[1]
        if o["dizin"]["durum"] == "hazir" and o["tam_metin"].get("durum") == "hazir":
            break
        time.sleep(0.5)
    ara = ek_js("/api/metin-ara?k=%s&q=%s" % (q(r["id"]), q("yemek")))[1]["sonuc"]
    sayfa = istek("/zim/%s/%s" % (q(r["id"]), yolq(ara[0]["yol"])), port=EK["port"])[0] if ara else 0
    EK["kucuk"] = r["id"]
    tamam = (on[0] == 200 and r.get("dogrulandi") and ayni and o.get("baslik") == asil["baslik"] and o.get("madde") == asil["madde"]
             and o["tam_metin"].get("durum") == "hazir" and len(ara) > 0 and sayfa == 200 and ek_dosyalar() == [os.path.basename(kaynak)])
    return sonuc(tamam, "ön denetim %d; ekleme %d (%s, %.1f MB, sağlaması doğrulandı: %s); kopya özgün dosyayla bire bir aynı: %s; kütüphanede “%s”, %d madde (özgünde %d); tam metin dizini: %s; “yemek” araması %d sonuç, ilk madde açıldı: %s; klasörde: %s" % (
        on[0], kod, r["id"][:24], r["boyut_mb"], r.get("dogrulandi"), ayni, o.get("baslik"), o.get("madde"), asil["madde"],
        o["tam_metin"].get("durum"), len(ara), sayfa == 200, ek_dosyalar()))


@senaryo("E3", "Uygun olmayan dosyalar reddediliyor: uzantısı yanlış, kitap olmayan, yarım kalmış, diske sığmayan, zaten kütüphanede olan; geride dosya kalmıyor")
def _():
    if "kucuk" not in EK:
        return sonuc(False, EK_YOK if not EK_VAR else "E2 çalışmadı")
    kaynak = zim_yolu(EK_KUCUK)
    with open(kaynak, "rb") as f:
        bas = f.read(80)
        ilk_mb = bas + f.read((1 << 20) - 80)
    boy = os.path.getsize(kaynak)
    dev = bytearray(bas)
    dev[8:24] = bytes(range(16))                      # başka bir kitapmış gibi
    struct.pack_into("<Q", dev, 72, 10 ** 15 - 16)    # ve çok büyük
    denemeler = [
        ("uzantısı .zim değil", ek_denetle(bas, "resim.png", boy), 400),
        ("içi kitap değil", ek_denetle(bytes(80), "bos.zim", boy), 400),
        ("yarım kalmış (boyu kısa)", ek_denetle(bas, "yarim.zim", boy - 4096), 400),
        ("diske sığmıyor", ek_denetle(bytes(dev), "dev.zim", 10 ** 15), 507),
        ("zaten kütüphanede", ek_denetle(kaynak, "baska-ad.zim"), 409),
        ("ön denetimsiz gönderilen çöp dosya", ek_gonder(os.urandom(300000), "cop.zim"), 400),
        ("ön denetimsiz gönderilen yarım dosya", ek_gonder(ilk_mb, "yarim.zim"), 400),
    ]
    yanlis = ["%s: %s bekleniyordu, %s geldi" % (ad, bek, r[0]) for ad, r, bek in denemeler if r[0] != bek]
    iletisiz = [ad for ad, r, _b in denemeler if not (r[1] or {}).get("hata")]
    time.sleep(0.5)
    temiz = ek_dosyalar() == [os.path.basename(kaynak)] and len(ek_kitaplar()) == 1
    return sonuc(not yanlis and not iletisiz and temiz, "%d deneme, hepsi reddedildi ve her biri nedenini söyledi: %s; örnek ileti: “%s”; klasörde yalnızca ilk kitap var: %s" % (
        len(denemeler), "evet" if not yanlis and not iletisiz else "HAYIR %s %s" % (yanlis, iletisiz), denemeler[4][1][1].get("hata", "")[:80], temiz))


@senaryo("E4", "Bozuk dosya eklenmiyor: ortasında tek bayt değişmiş kitap, sağlaması tutmadığı için reddediliyor")
def _():
    if "kucuk" not in EK:
        return sonuc(False, EK_YOK if not EK_VAR else "E2 çalışmadı")
    import shutil
    kaynak = zim_yolu(EK_IKINCI)
    bozuk = os.path.join(EK["gecici"], "bozuk.zim")
    shutil.copy(kaynak, bozuk)
    with open(bozuk, "r+b") as f:
        f.seek(os.path.getsize(bozuk) // 2)
        b = f.read(1)
        f.seek(-1, 1)
        f.write(bytes([b[0] ^ 0x01]))
    on = ek_denetle(bozuk, "bozuk.zim")
    once = ek_dosyalar()
    kod, r = ek_gonder(bozuk, "bozuk.zim")
    time.sleep(0.5)
    return sonuc(on[0] == 200 and kod == 422 and "sağlama" in (r or {}).get("hata", "") and ek_dosyalar() == once and len(ek_kitaplar()) == 1,
                 "tek bayt değiştirildi (%d MB'lık dosyanın ortasında); ön denetim %d (başlığı sağlam); kopyalama sonunda yanıt %s: “%s”; klasör ve kütüphane değişmedi: %s" % (
                     os.path.getsize(bozuk) >> 20, on[0], kod, (r or {}).get("hata", "")[:90], ek_dosyalar() == once))


@senaryo("E5", "Kopyalama yarıda kesilirse (tarayıcı kapanırsa) yarım dosya kalmıyor ve sonraki ekleme çalışıyor")
def _():
    if "kucuk" not in EK:
        return sonuc(False, EK_YOK if not EK_VAR else "E2 çalışmadı")
    kaynak = zim_yolu(EK_IKINCI)
    boy = os.path.getsize(kaynak)
    once = ek_dosyalar()
    s = socket.create_connection((HOST, EK["port"]))
    s.sendall(("POST /api/kitap-ekle?ad=kesik.zim HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nContent-Length: %d\r\nContent-Type: application/octet-stream\r\n\r\n" % (EK["port"], boy)).encode())
    with open(kaynak, "rb") as f:
        s.sendall(f.read(3 << 20))
    time.sleep(0.5)
    sirasinda = [d for d in ek_dosyalar() if d not in once]
    s.close()
    time.sleep(2)
    sonra = ek_dosyalar()
    kod, r = ek_gonder(kaynak, os.path.basename(kaynak))
    if kod == 200:
        EK["ikinci"] = r["id"]
    return sonuc(len(sirasinda) == 1 and sonra == once and kod == 200 and len(ek_kitaplar()) == 2,
                 "3 MB gönderilip bağlantı kapatıldı; o sırada klasörde: %s; kapandıktan sonra kalan fazladan dosya: %s; ardından aynı kitabın tam eklenmesi: %s; kütüphanede %d kitap" % (
                     sirasinda, [d for d in sonra if d not in once] or "yok", kod, len(ek_kitaplar())))


@senaryo("E6", "Güvenlik: dışarıdaki bir site kitap ekleyemiyor ve silemiyor; dosya adındaki klasör yolu veri klasörünün dışına çıkamıyor")
def _():
    if "ikinci" not in EK:
        return sonuc(False, EK_YOK if not EK_VAR else "E5 çalışmadı")
    yabanci = {"Origin": "http://kotu.example"}
    a = ek_denetle(zim_yolu(EK_ORTA), "x.zim", basliklar=yabanci)[0]
    b = ek_gonder(os.urandom(2000), "x.zim", yabanci)[0]
    c = ek_js("/api/kitap-sil", yontem="POST", govde={"k": EK["kucuk"]}, basliklar=yabanci)[0]
    duruyor = EK["kucuk"] in ek_kitaplar()
    kaynak = zim_yolu(EK_ORTA)
    kod, r = ek_gonder(kaynak, "..\\..\\kotu klasor/../Ad Soyad (1).zim")
    icerde = [d for d in ek_dosyalar() if d.startswith("Ad_Soyad")]
    disari = [d for d in os.listdir(EK["kok"]) + os.listdir(os.path.dirname(EK["kok"])) if "kotu" in d or "Ad Soyad" in d or "Ad_Soyad" in d]
    if kod == 200:
        EK["orta"] = r["id"]
    return sonuc(a == 403 and b == 403 and c == 403 and duruyor and kod == 200 and len(icerde) == 1 and not disari,
                 "yabancı siteden: ön denetim %d, ekleme %d, silme %d (kitap duruyor: %s); adı “..\\..\\kotu klasor/../Ad Soyad (1).zim” olan dosya: yanıt %s, kaydedildiği ad: %s, veri klasörünün dışında oluşan: %s" % (
                     a, b, c, duruyor, kod, icerde, disari or "yok"))


def _ek_dizin_dosyalari(kid):
    return sorted(d for d in os.listdir(EK["ddir"]) if d.startswith(kid + ".")) if os.path.isdir(EK["ddir"]) else []


@senaryo("E7", "Dizini kurulurken kitabı silme: kitap siliniyor, geride yarım dizin dosyası kalmıyor, uygulama çalışmaya devam ediyor")
def _():
    if "orta" not in EK:
        return sonuc(False, EK_YOK if not EK_VAR else "E6 çalışmadı")
    kid = EK["orta"]
    durum, son = "", time.time() + 40
    while time.time() < son:
        o = ek_js("/api/kitap?k=" + q(kid))[1]
        durum = "başlık dizini: %s, tam metin: %s %%%s" % (o["dizin"]["durum"], o["tam_metin"].get("durum"), o["tam_metin"].get("yuzde"))
        if o["tam_metin"].get("durum") in ("hazirlaniyor", "hazir"):
            break
        time.sleep(0.1)
    kurulurken = o["tam_metin"].get("durum") == "hazirlaniyor"
    kod, r = ek_js("/api/kitap-sil", yontem="POST", govde={"k": kid})
    time.sleep(5)
    kalan = _ek_dizin_dosyalari(kid)
    dosya = [d for d in ek_dosyalar() if d.startswith("Ad_Soyad")]
    ayakta = ek_js("/api/metin-ara?k=%s&q=yemek" % q(EK["kucuk"]))[0] == 200
    return sonuc(kurulurken and kod == 200 and not kalan and not dosya and kid not in ek_kitaplar() and ayakta,
                 "silme anında %s; yanıt %s (%s MB açıldı); 5 sn sonra bu kitaba ait dizin dosyası: %s; kitap dosyası: %s; öbür kitapta arama çalışıyor: %s" % (
                     durum, kod, (r or {}).get("silinen_mb"), kalan or "yok", dosya or "yok", ayakta))


@senaryo("E8", "Kitap silme: dosyası ve dizinleri gidiyor, o kadar yer açılıyor, kitap listeden ve aramadan çıkıyor, öbür kitaplar etkilenmiyor")
def _():
    import shutil
    if "ikinci" not in EK:
        return sonuc(False, EK_YOK if not EK_VAR else "E5 çalışmadı")
    try:
        kid = EK["kucuk"]
        son = time.time() + 120
        while time.time() < son:  # öbür kitabın dizinleri de bitsin: "etkilenmedi" ölçüsü için
            if all((k.get("tam_metin") == "hazir") for k in ek_kitaplar().values()):
                break
            time.sleep(0.5)
        yol = os.path.join(EK["zdir"], [d for d in ek_dosyalar() if kitap_bul("wikibooks") and d.startswith("wikibooks")][0])
        dizinler = _ek_dizin_dosyalari(kid)
        boy = os.path.getsize(yol) + sum(os.path.getsize(os.path.join(EK["ddir"], d)) for d in dizinler)
        obur_once = ek_js("/api/metin-ara?k=%s&q=hidrojen" % q(EK["ikinci"]))[1]["sonuc"]
        kod, r = ek_js("/api/kitap-sil", yontem="POST", govde={"k": kid})
        gitti = not os.path.exists(yol) and not _ek_dizin_dosyalari(kid)
        liste = kid in ek_kitaplar()
        sayfa = istek("/zim/%s/" % q(kid), port=EK["port"])[0]
        ozet = ek_js("/api/kitap?k=" + q(kid))[0]
        genel = [x for x in ek_js("/api/metin-ara?q=yemek")[1]["sonuc"] if x["kitap"] == kid]
        obur = ek_js("/api/metin-ara?k=%s&q=hidrojen" % q(EK["ikinci"]))[1]["sonuc"]
        yine = ek_js("/api/kitap-sil", yontem="POST", govde={"k": kid})[0]
        tamam = (kod == 200 and gitti and abs(r["silinen_mb"] - boy / 2 ** 20) < 0.2 and not liste and sayfa == 404 and ozet == 404 and not genel
                 and len(obur) > 0 and [x["yol"] for x in obur] == [x["yol"] for x in obur_once] and yine == 404)
        return sonuc(tamam, "silmeden önce kitap + %d dizin dosyası %.1f MB; yanıt %s, açılan yer %.1f MB; dosyalar gitti: %s; listede: %s; sayfası %s, giriş ekranı %s; genel aramada bu kitaptan sonuç: %d; öbür kitapta “hidrojen” araması aynı %d sonucu veriyor: %s; ikinci kez silme: %s" % (
            len(dizinler), boy / 2 ** 20, kod, r["silinen_mb"], gitti, liste, sayfa, ozet, len(genel), len(obur), [x["yol"] for x in obur] == [x["yol"] for x in obur_once], yine))
    finally:
        try:
            istek("/api/kapat", "POST", {}, port=EK["port"], zaman=5)
            EK["p"].wait(15)
        except Exception:
            EK["p"].kill()
        shutil.rmtree(EK["kok"], ignore_errors=True)
        shutil.rmtree(EK["gecici"], ignore_errors=True)


# ================================================================ V. İNDİRİLEN PAKETİN SAĞLAMASI VE KİTAP DENETLEME
# Ayrı bir İmece kopyası (geçici klasör) ve bu betiğin içinde çalışan yerel bir "kaynak sunucu" kullanılır:
# kaynak, istenirse bozuk, eksik ya da yavaş dosya verir. İnternet gerekmez; asıl kütüphaneye dokunulmaz.
import http.server
import threading
VD = {}
VD_VAR = bool(KITAPLAR) and istek("/api/kitap-denetle?k=" + q(KITAPLAR[0]["id"]))[0] == 200
VD_YOK = "bu sürümde indirilen paketin sağlaması denetlenmiyor"


class _Kaynak(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        ad = self.path.strip("/")
        d = VD["dosyalar"].get(ad)
        rng = self.headers.get("Range") or ""
        VD["istek"].setdefault(ad, []).append(rng)
        if d is None:
            return self.send_error(404)
        veri = d(len(VD["istek"][ad])) if callable(d) else d  # işlevse: kaçıncı istek olduğuna göre içerik
        bas = 0
        if rng.startswith("bytes="):
            bas = int(rng[6:].split("-")[0])
            if bas >= len(veri):
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % len(veri))
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (bas, len(veri) - 1, len(veri)))
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(veri) - bas))
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        try:
            for i in range(bas, len(veri), 65536):
                self.wfile.write(veri[i:i + 65536])
                if VD["yavas"].get(ad):
                    time.sleep(VD["yavas"][ad])
        except OSError:
            pass


def _vd_kur():
    import shutil
    with open(zim_yolu(EK_IKINCI), "rb") as f:
        iyi = f.read()
    with open(zim_yolu(EK_KUCUK), "rb") as f:
        yavas = f.read()
    bozuk = bytearray(iyi)
    bozuk[len(bozuk) // 2] ^= 0x01
    bozuk = bytes(bozuk)
    kport = PORT + 6
    VD.update(port=PORT + 5, kport=kport, iyi=iyi, yavas_veri=yavas, istek={}, yavas={"yavas.zim": 0.02},
              dosyalar={"iyi.zim": iyi, "bozuk.zim": bozuk, "kisa.zim": iyi[:-5000], "yavas.zim": yavas,
                        "duzelen.zim": lambda n: bozuk if n == 1 else iyi})
    VD["kaynak"] = http.server.ThreadingHTTPServer(("127.0.0.1", kport), _Kaynak)
    threading.Thread(target=VD["kaynak"].serve_forever, daemon=True).start()
    kok = tempfile.mkdtemp(prefix="imece-saglama-")
    shutil.copy(os.path.join(A.klasor, "imece.py"), kok)
    shutil.copytree(os.path.join(A.klasor, "uygulama"), os.path.join(kok, "uygulama"))
    kat = os.path.join(kok, "uygulama", "katalog.json")
    with open(kat, encoding="utf-8") as f:
        k = json.load(f)
    k["icerikler"] = [{"id": "t-" + ad, "baslik": "Deneme " + ad, "kategori": (k["icerikler"][0].get("kategori") or "kitap"), "profiller": [],
                       "tahmini_mb": 12, "lisans": "-", "tur": "dogrudan", "dil": "tr", "dosya": ad + ".zim",
                       "url": "http://127.0.0.1:%d/%s.zim" % (kport, ad)} for ad in ("iyi", "bozuk", "duzelen", "kisa", "yavas")]
    with open(kat, "w", encoding="utf-8") as f:
        json.dump(k, f, ensure_ascii=False)
    VD.update(kok=kok, zdir=os.path.join(kok, "veri", "zim"))
    VD["p"] = subprocess.Popen([sys.executable, os.path.join(kok, "imece.py"), "--port", str(VD["port"]), "--tarayici-acma"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _i in range(80):
        try:
            if istek("/api/durum", port=VD["port"], zaman=2)[0] == 200:
                return True
        except Exception:
            time.sleep(0.25)
    return False


def vd_js(yol, **kw):
    return js(yol, port=VD["port"], **kw)


def vd_bitene_kadar(sn=90):
    son = time.time() + sn
    while time.time() < son:
        d = vd_js("/api/durum")[1]
        if not d["is"]["aktif"]:
            return d
        time.sleep(0.3)
    return vd_js("/api/durum")[1]


def vd_indir(ad, sn=90):
    """Deneme paketini indirtir; bitince (durum, o paketle ilgili günlük satırları, klasördeki dosyalar) döner."""
    once = len(vd_js("/api/durum")[1]["is"]["log"])
    vd_js("/api/indir", yontem="POST", govde={"ids": ["t-" + ad]})
    time.sleep(0.5)
    d = vd_bitene_kadar(sn)
    return d, " | ".join(d["is"]["log"][-8:]), sorted(os.listdir(VD["zdir"]))


def vd_ayni(ad, veri):
    yol = os.path.join(VD["zdir"], ad)
    if not os.path.exists(yol):
        return False
    with open(yol, "rb") as f:
        return f.read() == veri


@senaryo("V1", "Sağlam inen paket: sağlaması denetlenip kütüphaneye giriyor; kayıtlara 'doğrulandı' yazılıyor")
def _():
    if not VD_VAR:
        return sonuc(False, VD_YOK)
    if not _vd_kur():
        return sonuc(False, "deneme kopyası başlatılamadı")
    d, gunluk, dosyalar = vd_indir("iyi")
    paket = [p for p in d["paketler"] if p["id"] == "t-iyi"][0]
    with open(os.path.join(VD["kok"], "veri", "durum.json"), encoding="utf-8") as f:
        kayit = json.load(f).get("t-iyi", {})
    kitap = [k["id"] for k in vd_js("/api/kitaplar")[1]]
    tamam = vd_ayni("iyi.zim", VD["iyi"]) and "sağlaması doğrulandı" in gunluk and paket["kurulu"] and kayit.get("dogrulandi") is True and kitap == ["iyi"] and dosyalar == ["iyi.zim"]
    return sonuc(tamam, "inen dosya kaynakla bire bir aynı: %s; günlük: “%s”; Paketler'de kurulu: %s; kayıtta doğrulandı: %s; kütüphanede: %s" % (
        vd_ayni("iyi.zim", VD["iyi"]), gunluk[-70:], paket["kurulu"], kayit.get("dogrulandi"), kitap))


@senaryo("V2", "Bozuk inen paket (tek baytı değişmiş) kütüphaneye girmiyor; bir kere daha denenip bırakılıyor, geride dosya kalmıyor")
def _():
    if "p" not in VD:
        return sonuc(False, VD_YOK if not VD_VAR else "V1 çalışmadı")
    d, gunluk, dosyalar = vd_indir("bozuk")
    paket = [p for p in d["paketler"] if p["id"] == "t-bozuk"][0]
    n = len(VD["istek"].get("bozuk.zim", []))
    tamam = dosyalar == ["iyi.zim"] and not paket["kurulu"] and n == 2 and "bozuk" in gunluk and "İki kere bozuk indi" in gunluk
    return sonuc(tamam, "kaynaktan %d kere istendi; klasörde: %s; Paketler'de kurulu: %s; günlük: “%s”" % (n, dosyalar, paket["kurulu"], gunluk[-230:]))


@senaryo("V3", "İlk seferde bozuk, ikincide sağlam gelen paket: kendiliğinden baştan indirilip ekleniyor")
def _():
    if "p" not in VD:
        return sonuc(False, VD_YOK if not VD_VAR else "V1 çalışmadı")
    d, gunluk, dosyalar = vd_indir("duzelen")
    n = len(VD["istek"].get("duzelen.zim", []))
    tamam = vd_ayni("duzelen.zim", VD["iyi"]) and n == 2 and "Baştan indiriliyor" in gunluk and "sağlaması doğrulandı" in gunluk and dosyalar == ["duzelen.zim", "iyi.zim"]
    return sonuc(tamam, "kaynaktan %d kere istendi (ilki bozuk verildi); sonunda inen dosya sağlam kaynakla aynı: %s; günlük: “%s”" % (
        n, vd_ayni("duzelen.zim", VD["iyi"]), gunluk[-200:]))


@senaryo("V4", "Eksik inen paket (kaynaktaki dosyanın sonu kesik) eklenmiyor")
def _():
    if "p" not in VD:
        return sonuc(False, VD_YOK if not VD_VAR else "V1 çalışmadı")
    d, gunluk, dosyalar = vd_indir("kisa")
    paket = [p for p in d["paketler"] if p["id"] == "t-kisa"][0]
    tamam = dosyalar == ["duzelen.zim", "iyi.zim"] and not paket["kurulu"] and "eksik" in gunluk
    return sonuc(tamam, "klasörde: %s; Paketler'de kurulu: %s; günlük: “%s”" % (dosyalar, paket["kurulu"], gunluk[-200:]))


@senaryo("V5", "Yarım kalan indirmenin diskteki parçası bozulursa: devam edince fark ediliyor, baştan indirilip sağlam ekleniyor")
def _():
    if "p" not in VD:
        return sonuc(False, VD_YOK if not VD_VAR else "V1 çalışmadı")
    vd_js("/api/indir", yontem="POST", govde={"ids": ["t-yavas"]})
    yarim = os.path.join(VD["zdir"], "yavas.zim.yarim")
    son = time.time() + 30
    while time.time() < son and not (os.path.exists(yarim) and os.path.getsize(yarim) > 3 << 20):
        time.sleep(0.1)
    vd_js("/api/durdur", yontem="POST", govde={})
    vd_bitene_kadar(20)
    boy = os.path.getsize(yarim)
    with open(yarim, "r+b") as f:  # diskteki yarım dosyanın ortasında tek bayt değişsin
        f.seek(boy // 2)
        b = f.read(1)
        f.seek(-1, 1)
        f.write(bytes([b[0] ^ 0x01]))
    VD["yavas"]["yavas.zim"] = 0
    vd_js("/api/devam", yontem="POST", govde={})
    time.sleep(0.5)
    d = vd_bitene_kadar(90)
    gunluk = " | ".join(d["is"]["log"][-8:])
    istekler = VD["istek"].get("yavas.zim", [])
    tamam = (vd_ayni("yavas.zim", VD["yavas_veri"]) and not os.path.exists(yarim) and len(istekler) == 3 and istekler[0] == ""
             and istekler[1].startswith("bytes=") and istekler[2] == "" and "bozuk" in gunluk and "sağlaması doğrulandı" in gunluk)
    return sonuc(tamam, "%d MB inmişken duraklatıldı, yarım dosyada tek bayt değiştirildi; kaynağa giden istekler: %s (baştan, kaldığı yerden, yeniden baştan); sonunda inen dosya kaynakla aynı: %s; günlük: “%s”" % (
        boy >> 20, [x or "baştan" for x in istekler], vd_ayni("yavas.zim", VD["yavas_veri"]), gunluk[-190:]))


@senaryo("V6", "Kitabı denetle: sağlam kitaba 'sağlam' diyor; diskte tek baytı bozulan kitaba 'bozuk' diyor; dışarıdan başlatılamıyor")
def _():
    import shutil
    if "p" not in VD:
        return sonuc(False, VD_YOK if not VD_VAR else "V1 çalışmadı")
    try:
        def denetle(kid):
            vd_js("/api/kitap-denetle?basla=1&k=" + q(kid))
            for _i in range(100):
                s = vd_js("/api/kitap-denetle?k=" + q(kid))[1]
                if s["durum"] != "suruyor":
                    return s
                time.sleep(0.1)
            return s
        a = denetle("iyi")
        yol = os.path.join(VD["zdir"], "iyi.zim")
        with open(yol, "r+b") as f:
            f.seek(os.path.getsize(yol) // 3)
            b = f.read(1)
            f.seek(-1, 1)
            f.write(bytes([b[0] ^ 0x80]))
        b2 = denetle("iyi")
        c = vd_js("/api/kitap-denetle?basla=1&k=iyi", basliklar={"Origin": "http://kotu.example"})[0]
        e = vd_js("/api/kitap-denetle?basla=1&k=olmayan-kitap")[0]
        tamam = a["durum"] == "saglam" and b2["durum"] == "bozuk" and "sağlama" in b2.get("neden", "") and c == 403 and e == 404
        return sonuc(tamam, "sağlam kitap: %s (%s sn); tek baytı değiştirildikten sonra: %s (%s); yabancı siteden başlatma: %s; olmayan kitap: %s" % (
            a["durum"], a.get("sure"), b2["durum"], b2.get("neden"), c, e))
    finally:
        try:
            istek("/api/kapat", "POST", {}, port=VD["port"], zaman=5)
            VD["p"].wait(15)
        except Exception:
            VD["p"].kill()
        VD["kaynak"].shutdown()
        shutil.rmtree(VD["kok"], ignore_errors=True)


@senaryo("V7", "Kütüphanedeki en büyük kitabın denetimi: sonuç ve süre")
def _():
    if not VD_VAR:
        return sonuc(False, VD_YOK)
    k = max(KITAPLAR, key=lambda x: x["boyut_mb"])
    js("/api/kitap-denetle?basla=1&k=" + q(k["id"]))
    s = {}
    for _i in range(3000):
        s = js("/api/kitap-denetle?k=" + q(k["id"]))[1]
        if s["durum"] != "suruyor":
            break
        time.sleep(0.2)
    return sonuc(s.get("durum") == "saglam", "%s (%d MB): %s, %s sn" % (k["baslik"], k["boyut_mb"], s.get("durum"), s.get("sure")))


# ================================================================ N. AĞ PAYLAŞIMI (uygulamanın içinden açıp kapatma)
# Ayrı bir İmece kopyasında koşulur. "Ağdaki cihaz", bu bilgisayarın ağ adresine bağlanılarak taklit edilir:
# sunucu o isteği ağdan gelmiş görür (istemci adresi 127.0.0.1 değildir). Gerçek ikinci bir cihaz yoktur.
AGT = {}
AG_VAR = "ag" in DURUM
AG_YOK = "bu sürümde ağ paylaşımı uygulamanın içinden açılamıyor (komut satırı gerekir)"


def _bu_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None
    finally:
        s.close()


def _baglanir(ip, port):
    try:
        socket.create_connection((ip, port), timeout=2).close()
        return True
    except OSError:
        return False


def _agt_baslat():
    AGT["p"] = subprocess.Popen([sys.executable, os.path.join(AGT["kok"], "imece.py"), "--port", str(AGT["port"]), "--tarayici-acma"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _i in range(80):
        try:
            if istek("/api/durum", port=AGT["port"], zaman=2)[0] == 200:
                return True
        except Exception:
            time.sleep(0.25)
    return False


def _agt_kur():
    import shutil
    kok = tempfile.mkdtemp(prefix="imece-ag-")
    shutil.copy(os.path.join(A.klasor, "imece.py"), kok)
    shutil.copytree(os.path.join(A.klasor, "uygulama"), os.path.join(kok, "uygulama"))
    os.makedirs(os.path.join(kok, "veri", "zim"))
    shutil.copy(zim_yolu(EK_KUCUK), os.path.join(kok, "veri", "zim"))
    AGT.update(kok=kok, port=PORT + 7, ip=_bu_ip(), kid=EK_KUCUK)
    return _agt_baslat()


def agt(yol, agdan=False, **kw):
    return js(yol, port=AGT["port"], host=AGT["ip"] if agdan else HOST, **kw)


@senaryo("N1", "Ağ paylaşımı varsayılan olarak kapalı: bu bilgisayarın ağ adresinden İmece'ye bağlanılamıyor")
def _():
    if not AG_VAR:
        return sonuc(False, AG_YOK)
    if not _bu_ip():
        return "ATLANDI", "bu bilgisayar bir ağa bağlı değil; ağ senaryoları koşulamadı"
    if not _agt_kur():
        return sonuc(False, "deneme kopyası başlatılamadı")
    d = agt("/api/durum")[1]["ag"]
    baglandi = _baglanir(AGT["ip"], AGT["port"])
    return sonuc(d["acik"] is False and not d["adres"] and not baglandi, "durum: %s; ağ adresi %s:%d bağlantı kabul ediyor: %s" % (d, AGT["ip"], AGT["port"], baglandi))


@senaryo("N2", "Paylaşımı aç: uygulama adresi gösteriyor; ağ adresinden kütüphane okunuyor (ana sayfa, kitap listesi, arama, madde)")
def _():
    if "p" not in AGT:
        return ("ATLANDI", "ağ yok") if AG_VAR and not _bu_ip() else sonuc(False, AG_YOK if not AG_VAR else "N1 çalışmadı")
    kod, r = agt("/api/ag", yontem="POST", govde={"ac": True})
    beklenen = "http://%s:%d/" % (AGT["ip"], AGT["port"])
    son = time.time() + 60
    while time.time() < son and agt("/api/kitap?k=" + q(AGT["kid"]))[1]["dizin"]["durum"] != "hazir":
        time.sleep(0.3)
    ana = istek("/uygulama/index.html", host=AGT["ip"], port=AGT["port"])[0]
    kitaplar = agt("/api/kitaplar", agdan=True)[1]
    ara = agt("/api/ara?k=%s&q=yemek" % q(AGT["kid"]), agdan=True)[1]
    sayfa = istek("/zim/%s/%s" % (q(AGT["kid"]), yolq(ara[0]["yol"])), host=AGT["ip"], port=AGT["port"])[0] if ara else 0
    dur = agt("/api/durum", agdan=True)[1]
    tamam = (kod == 200 and r["acik"] and r["adres"] == beklenen and ana == 200 and len(kitaplar) == 1 and len(ara) > 0 and sayfa == 200
             and dur["yerel"] is False and dur["veri"] == "")
    return sonuc(tamam, "yanıt %s, adres %s (beklenen %s); ağ adresinden: ana sayfa %s, %d kitap, “yemek” araması %d sonuç, madde %s; o cihaza göre yerel: %s, klasör yolu gösteriliyor: %s" % (
        kod, r.get("adres"), beklenen, ana, len(kitaplar), len(ara), sayfa, dur["yerel"], bool(dur["veri"])))


@senaryo("N3", "Ağdan bağlanan cihaz yalnızca okuyabiliyor: silme, ekleme, ayar, indirme, paylaşımı kapatma ve İmece'yi kapatma reddediliyor")
def _():
    if "p" not in AGT:
        return ("ATLANDI", "ağ yok") if AG_VAR and not _bu_ip() else sonuc(False, AG_YOK if not AG_VAR else "N1 çalışmadı")
    denemeler = [
        ("kitap sil", agt("/api/kitap-sil", agdan=True, yontem="POST", govde={"k": AGT["kid"]})[0]),
        ("kitap ekleme ön denetimi", agt("/api/kitap-ekle-denetle", agdan=True, yontem="POST", govde={"ad": "x.zim", "boy": 1, "bas": ""})[0]),
        ("ayar değiştir", agt("/api/ayar", agdan=True, yontem="POST", govde={"tam_metin": False})[0]),
        ("indirme başlat", agt("/api/indir", agdan=True, yontem="POST", govde={"ids": ["x"]})[0]),
        ("tam metin dizinlerini sil", agt("/api/tam-metin-sil", agdan=True, yontem="POST", govde={})[0]),
        ("paylaşımı kapat", agt("/api/ag", agdan=True, yontem="POST", govde={"ac": False})[0]),
        ("İmece'yi kapat", agt("/api/kapat", agdan=True, yontem="POST", govde={})[0]),
        ("kitap denetimini başlat", agt("/api/kitap-denetle?basla=1&k=" + q(AGT["kid"]), agdan=True)[0]),
    ]
    time.sleep(1)
    d = agt("/api/durum")[1]
    duruyor = len(agt("/api/kitaplar")[1]) == 1
    tamam = all(k == 403 for _a, k in denemeler) and duruyor and d["ag"]["acik"] and d["tam_metin"]["acik"]
    return sonuc(tamam, "%d yönetim isteğinin yanıtları: %s; kitap duruyor: %s; paylaşım hâlâ açık: %s; İmece çalışıyor: evet" % (
        len(denemeler), ", ".join("%s %s" % x for x in denemeler), duruyor, d["ag"]["acik"]))


@senaryo("N4", "Paylaşımı kapat: ağ adresi kapanıyor, bu bilgisayardan kullanım sürüyor; yabancı bir site paylaşımı açamıyor")
def _():
    if "p" not in AGT:
        return ("ATLANDI", "ağ yok") if AG_VAR and not _bu_ip() else sonuc(False, AG_YOK if not AG_VAR else "N1 çalışmadı")
    once = _baglanir(AGT["ip"], AGT["port"])
    kod, r = agt("/api/ag", yontem="POST", govde={"ac": False})
    time.sleep(0.5)
    sonra = _baglanir(AGT["ip"], AGT["port"])
    yerel = agt("/api/kitaplar")[0]
    yabanci = agt("/api/ag", yontem="POST", govde={"ac": True}, basliklar={"Origin": "http://kotu.example"})[0]
    hala_kapali = not agt("/api/durum")[1]["ag"]["acik"] and not _baglanir(AGT["ip"], AGT["port"])
    return sonuc(once and kod == 200 and r["acik"] is False and not sonra and yerel == 200 and yabanci == 403 and hala_kapali,
                 "kapatmadan önce ağ adresi açık: %s; kapatma yanıtı %s; sonra ağ adresi açık: %s; bu bilgisayardan kullanım: %s; yabancı siteden açma isteği: %s (paylaşım kapalı kaldı: %s)" % (
                     once, kod, sonra, yerel, yabanci, hala_kapali))


@senaryo("N5", "Paylaşım kalıcı değil: açıkken İmece kapatılıp yeniden açılınca kapalı başlıyor")
def _():
    import shutil
    if "p" not in AGT:
        return ("ATLANDI", "ağ yok") if AG_VAR and not _bu_ip() else sonuc(False, AG_YOK if not AG_VAR else "N1 çalışmadı")
    try:
        agt("/api/ag", yontem="POST", govde={"ac": True})
        acikti = _baglanir(AGT["ip"], AGT["port"])
        istek("/api/kapat", "POST", {}, port=AGT["port"], zaman=5)
        AGT["p"].wait(15)
        kapaninca = _baglanir(AGT["ip"], AGT["port"])
        yeniden = _agt_baslat()
        d = agt("/api/durum")[1]["ag"]
        acik = _baglanir(AGT["ip"], AGT["port"])
        return sonuc(acikti and not kapaninca and yeniden and d["acik"] is False and not acik,
                     "kapatmadan önce ağ adresi açık: %s; İmece kapanınca: %s; yeniden açılınca durum %s, ağ adresi açık: %s" % (acikti, kapaninca, d, acik))
    finally:
        try:
            istek("/api/kapat", "POST", {}, port=AGT["port"], zaman=5)
            AGT["p"].wait(15)
        except Exception:
            AGT["p"].kill()
        shutil.rmtree(AGT["kok"], ignore_errors=True)


# ================================================================ K. REHBERLERİN KAYNAK VE ONAY KAYITLARI
def _rehber_denetle(klasor):
    c = subprocess.run([sys.executable, os.path.join(A.klasor, "gelistirme", "rehber_onay.py"), klasor, "denetle", "--json"],
                       capture_output=True, text=True, encoding="utf-8")
    return json.loads(c.stdout) if c.stdout.strip().startswith("{") else {"bolumler": {}, "sorun": ["araç çalışmadı: " + (c.stderr or c.stdout)[-200:]]}


@senaryo("K10", "Rehber kayıtları tutarlı: her kaynaklı bölümde her kutu bir kaynağa bağlı, atıf yapılan her kaynak listede, eksik alan yok; bölüm özetleri bağımsız hesapla aynı")
def _():
    arac = os.path.join(A.klasor, "gelistirme", "rehber_onay.py")
    if not os.path.exists(arac):
        return sonuc(False, "bu sürümde rehberlerin kaynak/onay kaydı yok (rehber metinleri kaynaksız)")
    r = _rehber_denetle(A.klasor)
    with open(os.path.join(A.klasor, "uygulama", "index.html"), "rb") as f:
        sayfa = f.read()
    import hashlib as _h
    farkli = []
    for ad, k in r["bolumler"].items():
        a, b = sayfa.find(("<!--rehber:%s-->" % ad).encode()), sayfa.find(("<!--/rehber:%s-->" % ad).encode())
        if a >= 0 and b > a:  # bağımsız özet: işaretler arası baytlar
            oz = _h.sha256(sayfa[a + len("<!--rehber:%s-->" % ad):b]).hexdigest()
            if oz != k["ozet"]:
                farkli.append(ad)
    kaynakli = sorted(ad for ad, k in r["bolumler"].items() if k["durum"] == "kaynakli")
    taslak = sorted(ad for ad, k in r["bolumler"].items() if k["durum"] != "kaynakli")
    onayli = sorted(ad for ad, k in r["bolumler"].items() if k["onay"] != "yok")
    return sonuc(not r["sorun"] and not farkli and len(r["bolumler"]) >= 10,
                 "%d bölüm: kaynaklı %d (%s), taslak %d (%s), onay kaydı olan %d; toplam %d kaynak; tutarsızlık: %s; özeti bağımsız hesapla tutmayan: %s" % (
                     len(r["bolumler"]), len(kaynakli), ", ".join(kaynakli) or "-", len(taslak), ", ".join(taslak) or "-", len(onayli),
                     sum(k["kaynak"] for k in r["bolumler"].values()), r["sorun"][:3] or "yok", farkli or "yok"))


@senaryo("K11", "Onay metne bağlı: doğru özetle kaydedilen onay geçerli; metinde tek harf değişince geçersiz; kaynaksız ya da eksik kayıtlar yakalanıyor")
def _():
    import shutil
    arac = os.path.join(A.klasor, "gelistirme", "rehber_onay.py")
    if not os.path.exists(arac):
        return sonuc(False, "bu sürümde rehberlerin kaynak/onay kaydı yok")
    gecici = tempfile.mkdtemp(prefix="imece-rehber-")
    try:
        shutil.copytree(os.path.join(A.klasor, "uygulama"), os.path.join(gecici, "uygulama"))
        kyol, syol = os.path.join(gecici, "uygulama", "rehber-kaynak.js"), os.path.join(gecici, "uygulama", "index.html")
        ham = open(kyol, encoding="utf-8").read()
        bas, veri = ham[:ham.index("window.REHBER_KAYNAK")], json.loads(ham[ham.index("{", ham.index("window.REHBER_KAYNAK")):ham.rindex("}") + 1])

        def yaz(v):
            open(kyol, "w", encoding="utf-8", newline="\n").write(bas + "window.REHBER_KAYNAK = " + json.dumps(v, ensure_ascii=False) + ";\n")
        ilk = _rehber_denetle(gecici)
        hedef = next((ad for ad, k in ilk["bolumler"].items() if k["durum"] == "kaynakli" and not veri["bolumler"][ad].get("dosya")), None)
        if not hedef:
            return sonuc(False, "denenecek kaynaklı bölüm yok")
        v = json.loads(json.dumps(veri))
        v["bolumler"][hedef]["onay"] = {"ad": "Deneme Uzmanı", "unvan": "Dr.", "kurum": "Deneme", "tarih": "2026-11-18", "ozet": ilk["bolumler"][hedef]["ozet"]}
        yaz(v)
        a = _rehber_denetle(gecici)
        sayfa = open(syol, encoding="utf-8").read()
        i = sayfa.index("<!--rehber:%s-->" % hedef) + len("<!--rehber:%s-->" % hedef)
        j = sayfa.index("<li>", i)
        open(syol, "w", encoding="utf-8", newline="\n").write(sayfa[:j + 4] + "X" + sayfa[j + 4:])  # metne tek harf ekle
        b = _rehber_denetle(gecici)
        open(syol, "w", encoding="utf-8", newline="\n").write(sayfa)
        v2 = json.loads(json.dumps(veri))
        v2["bolumler"][hedef]["kaynaklar"] = v2["bolumler"][hedef]["kaynaklar"][1:]  # atıf yapılan bir kaynağı listeden çıkar
        yaz(v2)
        c = _rehber_denetle(gecici)
        v3 = json.loads(json.dumps(veri))
        v3["bolumler"][hedef]["kaynaklar"][0]["adres"] = ""
        v3["bolumler"]["x_taslak"] = {"durum": "kaynakli", "gozden": "2026-11-18", "kaynaklar": [], "onay": None, "dosya": "rehberler/kanama.js"}
        yaz(v3)
        d = _rehber_denetle(gecici)
        tamam = (not ilk["sorun"] and a["bolumler"][hedef]["onay"] == "gecerli" and not a["sorun"]
                 and b["bolumler"][hedef]["onay"] == "gecersiz" and any("onay geçersiz" in s for s in b["sorun"])
                 and any("listede yok" in s for s in c["sorun"]) and any("eksik alan" in s for s in d["sorun"]) and any("kaynak yok" in s for s in d["sorun"]))
        return sonuc(tamam, "“%s” bölümüne doğru özetle onay: %s, sorun %d; metne tek harf eklenince: %s (“%s”); kaynak listeden çıkarılınca: “%s”; adresi boş kaynak ve kaynaksız 'kaynaklı' bölüm: %d sorun" % (
            hedef, a["bolumler"][hedef]["onay"], len(a["sorun"]), b["bolumler"][hedef]["onay"], (b["sorun"] or [""])[0][:70],
            (c["sorun"] or [""])[0][:70], len(d["sorun"])))
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


# ================================================================ X. BAŞKA BİR İMECE'DEN KİTAP ALMA  ·  O. NOTLAR
# İki ayrı İmece kopyası: "veren" (Vikikitap'lı, paylaşımı açık) ve "alan" (boş kütüphane). Asıl kütüphaneye dokunulmaz.
XT = {}
X_VAR = bool(KITAPLAR) and "imza" in KITAPLAR[0]
X_YOK = "bu sürümde başka bir İmece'den kitap alma / not yok"


def _xt_baslat(ad, port, kitapli):
    import shutil
    kok = tempfile.mkdtemp(prefix="imece-%s-" % ad)
    shutil.copy(os.path.join(A.klasor, "imece.py"), kok)
    shutil.copytree(os.path.join(A.klasor, "uygulama"), os.path.join(kok, "uygulama"))
    os.makedirs(os.path.join(kok, "veri", "zim"))
    if kitapli:
        shutil.copy(zim_yolu(EK_KUCUK), os.path.join(kok, "veri", "zim"))
    p = subprocess.Popen([sys.executable, os.path.join(kok, "imece.py"), "--port", str(port), "--tarayici-acma"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    XT[ad] = {"kok": kok, "port": port, "p": p}
    for _i in range(80):
        try:
            if istek("/api/durum", port=port, zaman=2)[0] == 200:
                return True
        except Exception:
            time.sleep(0.25)
    return False


def xv(yol, **kw):  # veren
    return js(yol, port=XT["veren"]["port"], **kw)


def xa(yol, **kw):  # alan
    return js(yol, port=XT["alan"]["port"], **kw)


@senaryo("X1", "Kitap dosyası ağdan parça parça veriliyor: tamamı özgünle aynı, 'kaldığı yerden' isteği doğru yerden başlıyor")
def _():
    if not X_VAR:
        return sonuc(False, X_YOK)
    ip = _bu_ip()
    if not ip:
        return "ATLANDI", "bu bilgisayar bir ağa bağlı değil"
    if not (_xt_baslat("veren", PORT + 8, True) and _xt_baslat("alan", PORT + 9, False)):
        return sonuc(False, "deneme kopyaları başlatılamadı")
    XT["ip"] = ip
    XT["adres"] = "%s:%d" % (ip, XT["veren"]["port"])
    xv("/api/ag", yontem="POST", govde={"ac": True})
    with open(zim_yolu(EK_KUCUK), "rb") as f:
        ozgun = f.read()
    yol = "/api/kitap-dosya?k=" + q(EK_KUCUK)
    k1, b1, tam = istek(yol, host=ip, port=XT["veren"]["port"])
    k2, b2, parca = istek(yol, host=ip, port=XT["veren"]["port"], basliklar={"Range": "bytes=1000000-"})
    k3 = istek(yol, host=ip, port=XT["veren"]["port"], basliklar={"Range": "bytes=%d-" % len(ozgun)})[0]
    k4 = istek("/api/kitap-dosya?k=olmayan", host=ip, port=XT["veren"]["port"])[0]
    tamam = k1 == 200 and tam == ozgun and k2 == 206 and parca == ozgun[1000000:] and b2.get("content-range") == "bytes 1000000-%d/%d" % (len(ozgun) - 1, len(ozgun)) and k3 == 416 and k4 == 404
    return sonuc(tamam, "tamamı %s, %d bayt, özgünle aynı: %s; 1.000.000. bayttan itibaren: %s, parça doğru: %s (%s); dosya sonundan ötesi: %s; olmayan kitap: %s" % (
        k1, len(tam), tam == ozgun, k2, parca == ozgun[1000000:], b2.get("content-range"), k3, k4))


@senaryo("X2", "Başka İmece'nin kitap listesi: yazılan adres biçimleri anlaşılıyor; yerel ağ dışındaki adresler ve yabancı siteler reddediliyor")
def _():
    if "alan" not in XT:
        return ("ATLANDI", "ağ yok") if X_VAR and not _bu_ip() else sonuc(False, X_YOK if not X_VAR else "X1 çalışmadı")
    iyi = [XT["adres"], "http://" + XT["adres"] + "/", "  " + XT["adres"] + "/uygulama/index.html#ayarlar  "]
    r = [xa("/api/komsu?adres=" + q(a)) for a in iyi]
    kotu = ["8.8.8.8:80", "example.com", "http://[::1]:8642", "ftp://192.168.1.1", "192.168.1.999", ""]
    rk = [xa("/api/komsu?adres=" + q(a))[0] for a in kotu]
    yabanci = xa("/api/komsu?adres=" + q(XT["adres"]), basliklar={"Origin": "http://kotu.example"})[0]
    liste = r[0][1].get("kitaplar", []) if r[0][0] == 200 else []
    tamam = all(x[0] == 200 and len(x[1]["kitaplar"]) == 1 for x in r) and liste and liste[0]["var"] is False and all(k == 400 for k in rk) and yabanci == 403
    return sonuc(tamam, "3 yazım biçiminin yanıtları: %s; listede: %s; reddedilen adresler %s → %s; yabancı siteden: %s" % (
        [x[0] for x in r], ["%s (%s MB, bizde var: %s)" % (k["baslik"], k["boyut_mb"], k["var"]) for k in liste], kotu, rk, yabanci))


@senaryo("X3", "Kitap alma: öbür İmece'deki kitap buraya kopyalanıyor, sağlaması doğrulanıyor, kütüphaneye giriyor; ikinci kez alınmıyor")
def _():
    if "alan" not in XT:
        return ("ATLANDI", "ağ yok") if X_VAR and not _bu_ip() else sonuc(False, X_YOK if not X_VAR else "X1 çalışmadı")
    kod, r = xa("/api/komsu-al", yontem="POST", govde={"adres": XT["adres"], "ids": [EK_KUCUK]})
    d, son = {}, time.time() + 120
    time.sleep(0.5)
    while time.time() < son:
        d = xa("/api/durum")[1]
        if not d["is"]["aktif"]:
            break
        time.sleep(0.3)
    gunluk = " | ".join(d["is"]["log"][-3:])
    hedef = os.path.join(XT["alan"]["kok"], "veri", "zim", os.path.basename(zim_yolu(EK_KUCUK)))
    ayni = os.path.exists(hedef) and sha(hedef) == sha(zim_yolu(EK_KUCUK))
    o, son = {}, time.time() + 60
    while time.time() < son:
        kod2, o = xa("/api/kitap?k=" + q(EK_KUCUK))
        if kod2 == 200 and o["dizin"]["durum"] == "hazir":
            break
        time.sleep(0.3)
    asil = js("/api/kitap?k=" + q(EK_KUCUK))[1]
    sonra = xa("/api/komsu?adres=" + q(XT["adres"]))[1]["kitaplar"][0]["var"]
    yine = xa("/api/komsu-al", yontem="POST", govde={"adres": XT["adres"], "ids": [EK_KUCUK]})[1]
    tamam = kod == 200 and r["adet"] == 1 and ayni and "sağlaması doğrulandı" in gunluk and o.get("madde") == asil["madde"] and sonra is True and yine.get("adet") == 0
    return sonuc(tamam, "sıraya alınan: %s; kopya özgünle bire bir aynı: %s; günlük: “%s”; kütüphanede %s madde (özgünde %d); liste artık 'sende var' diyor: %s; ikinci istekte sıraya alınan: %s" % (
        r.get("adet"), ayni, gunluk[-60:], o.get("madde"), asil["madde"], sonra, yine.get("adet")))


@senaryo("X4", "Öbür İmece paylaşımı kapatmışsa: anlaşılır bir ileti geliyor, hiçbir şey sıraya girmiyor")
def _():
    if "alan" not in XT:
        return ("ATLANDI", "ağ yok") if X_VAR and not _bu_ip() else sonuc(False, X_YOK if not X_VAR else "X1 çalışmadı")
    xv("/api/ag", yontem="POST", govde={"ac": False})
    time.sleep(0.5)
    kod, r = xa("/api/komsu?adres=" + q(XT["adres"]))
    kod2, r2 = xa("/api/komsu-al", yontem="POST", govde={"adres": XT["adres"], "ids": [EK_KUCUK]})
    return sonuc(kod == 502 and "paylaşımı kapalı" in r.get("hata", "") and kod2 == 502 and not xa("/api/durum")[1]["is"]["aktif"],
                 "liste isteği %s: “%s…”; alma isteği %s" % (kod, r.get("hata", "")[:90], kod2))


@senaryo("O1", "Notlar: yazılıyor, okunuyor, değişiyor, boşaltınca siliniyor; dosyada duruyor; ağdan ya da yabancı siteden görülemiyor")
def _():
    import shutil
    if "alan" not in XT:
        return ("ATLANDI", "ağ yok") if X_VAR and not _bu_ip() else sonuc(False, X_YOK if not X_VAR else "X1 çalışmadı")
    try:
        yol = "C/Yemek:Mercimek_çorbası"
        a = xa("/api/not", yontem="POST", govde={"kitap": EK_KUCUK, "yol": yol, "baslik": "Mercimek çorbası", "metin": "İlk not: şiir gibi çorba, ğüşıöç."})
        b = xa("/api/not?k=%s&yol=%s" % (q(EK_KUCUK), q(yol)))[1]
        xa("/api/not", yontem="POST", govde={"kitap": EK_KUCUK, "yol": yol, "baslik": "Mercimek çorbası", "metin": "Değişti."})
        xa("/api/not", yontem="POST", govde={"kitap": "olmayan-kitap", "yol": "C/X", "baslik": "X", "metin": "y" * 50000})
        liste = xa("/api/notlar")[1]
        with open(os.path.join(XT["alan"]["kok"], "veri", "notlar.json"), encoding="utf-8") as f:
            dosya = json.load(f)
        uzun = [n for n in liste if n["kitap"] == "olmayan-kitap"][0]
        yabanci = xa("/api/notlar", basliklar={"Origin": "http://kotu.example"})[0]
        yabanci_yaz = xa("/api/not", yontem="POST", govde={"kitap": EK_KUCUK, "yol": yol, "metin": "ele geçirildi"}, basliklar={"Origin": "http://kotu.example"})[0]
        xa("/api/ag", yontem="POST", govde={"ac": True})
        agdan = js("/api/notlar", host=XT["ip"], port=XT["alan"]["port"])[0]
        agdan_tek = js("/api/not?k=%s&yol=%s" % (q(EK_KUCUK), q(yol)), host=XT["ip"], port=XT["alan"]["port"])[0]
        xa("/api/not", yontem="POST", govde={"kitap": EK_KUCUK, "yol": yol, "metin": "  "})
        sonra = xa("/api/notlar")[1]
        degisen = [n for n in liste if n["yol"] == yol][0]
        tamam = (a[0] == 200 and b["metin"].startswith("İlk not") and degisen["metin"] == "Değişti." and degisen["var"] is True and uzun["var"] is False
                 and len(uzun["metin"]) == 20000 and len(dosya) == 2 and yabanci == 403 and yabanci_yaz == 403 and agdan == 403 and agdan_tek == 403
                 and len(sonra) == 1 and sonra[0]["kitap"] == "olmayan-kitap")
        return sonuc(tamam, "yazılan okundu: “%s”; değiştirilince: “%s”; kitabı olmayan not işaretli: %s; 50.000 harflik not %d harfe kesildi; dosyada %d not; yabancı siteden okuma %s, yazma %s; ağdan liste %s, tek not %s; boşaltınca kalan: %d" % (
            b["metin"][:24], degisen["metin"], uzun["var"] is False, len(uzun["metin"]), len(dosya), yabanci, yabanci_yaz, agdan, agdan_tek, len(sonra)))
    finally:
        for ad in ("veren", "alan"):
            try:
                istek("/api/kapat", "POST", {}, port=XT[ad]["port"], zaman=5)
                XT[ad]["p"].wait(15)
            except Exception:
                XT[ad]["p"].kill()
            shutil.rmtree(XT[ad]["kok"], ignore_errors=True)


# ================================================================ Y. AYARLAR / FLASH
@senaryo("Y1", "Veri klasörünü değiştir ve geri al: kitaplar kayboluyor, sonra geri geliyor")
def _():
    gecici = tempfile.mkdtemp(prefix="imece-veri-")
    try:
        k1, r1 = js("/api/ayar", yontem="POST", govde={"veri": gecici})
        n1 = len(js("/api/kitaplar")[1])
    finally:
        k2, r2 = js("/api/ayar", yontem="POST", govde={"veri": VERI})
    n2 = len(js("/api/kitaplar")[1])
    import shutil
    shutil.rmtree(gecici, ignore_errors=True)
    return sonuc(k1 == 200 and n1 == 0 and n2 == KITAP_SAYISI, "yeni klasörde %d kitap, geri alınca %d kitap" % (n1, n2))


# ---- 0.19: paket kataloğunun kuralları ve sanat galerileri ----
@senaryo("G1", "Paket kataloğu: ticari kullanımı ya da türevi yasaklayan lisanslı içerik yok; hazır seçimlerde resimsiz Vikipedi yok; her seçimde sanat ve müzik var; sanat içerikleri kamu malı diye işaretli")
def _():
    with open(os.path.join(A.klasor, "uygulama", "katalog.json"), encoding="utf-8") as f:
        k = json.load(f)
    ic = k["icerikler"]
    if not any(x.get("tur") == "commons" for x in ic):
        return sonuc(False, "bu sürümde sanat galerisi yok")
    yasak = [x["id"] for x in ic if re.search(r"\bN[CD]\b|NC-|ND\b", x.get("lisans") or "")]
    resimsiz = [x["id"] for x in ic if x.get("flavour") in ("nopic", "mini") and x["profiller"]]
    sayilar = {p: (len([x for x in ic if p in x["profiller"]]), len([x for x in ic if p in x["profiller"] and x["kategori"] == "sanat"]),
                   len([x for x in ic if p in x["profiller"] and x["kategori"] == "muzik"])) for p in ("mini", "standart", "tam")}
    sanat = [x for x in ic if x["kategori"] == "sanat"]
    sanat_iyi = all(x["tur"] == "commons" and x.get("commons_kategori") and "Kamu malı" in x.get("lisans", "") for x in sanat)
    lisanssiz = [x["id"] for x in ic if not x.get("lisans")]
    sunucu = {x["id"] for x in js("/api/durum")[1]["paketler"]}
    kimlik_tek = len({x["id"] for x in ic}) == len(ic)
    return sonuc(not yasak and not resimsiz and all(a > 0 and b > 0 and c > 0 for a, b, c in sayilar.values()) and sanat_iyi and not lisanssiz and sunucu == {x["id"] for x in ic} and kimlik_tek,
                 "%d içerik; ticari olmayan / türev yasak lisanslı: %s; hazır seçimde resimsiz: %s; seçimlerde (içerik, sanat, müzik): %s; %d sanat içeriğinin hepsi kamu malı Commons kategorisi: %s; lisansı yazılmamış: %s; sunucu aynı listeyi veriyor: %s" % (
                     len(ic), yasak or "yok", resimsiz or "yok", ", ".join("%s %d/%d/%d" % ((p,) + sayilar[p]) for p in sayilar), len(sanat), sanat_iyi, lisanssiz or "yok", sunucu == {x["id"] for x in ic}))


if A.indirme:
    @senaryo("G2", "Sanat galerisi indiriliyor: resimler geliyor, her eserin künyesinde sanatçı, kamu malı lisansı ve kaynak sayfası var; yabancı site ve geçersiz ad galeri silemiyor")
    def _():
        if istek("/api/sanat")[0] != 200:
            return sonuc(False, "bu sürümde sanat galerisi yok")
        gid = "sanat-osman-hamdi"
        def galeri():
            return next((g for g in js("/api/sanat")[1] if g["id"] == gid), None)
        g0 = galeri()
        if not g0 or len(g0["eserler"]) < 3:  # yoksa ya da yarımsa indir (yarım kalan kaldığı yerden sürer)
            js("/api/indir", yontem="POST", govde={"ids": [gid]})
            for _i in range(240):
                time.sleep(1)
                if not js("/api/durum")[1]["is"]["aktif"]:
                    break
        g = galeri()
        if not g:
            return "ATLANDI", "Wikimedia Commons'tan tek resim bile indirilemedi (istekler geri çevrildi); kayıt: %s" % js("/api/durum")[1]["is"]["log"][-1:]
        iyi, boy = 0, 0
        for e in g["eserler"]:
            kod, b, v = istek("/veri/sanat/%s/%s" % (q(gid), q(e["dosya"])))
            boy += len(v)
            if kod == 200 and (v[:2] == b"\xff\xd8" or v[:4] == b"\x89PNG") and re.match(r"(?i)public domain|cc0|pd", e.get("lisans", "")) \
                    and e.get("kaynak", "").startswith("https://commons.wikimedia.org/wiki/File:") and e.get("ad") and e.get("sanatci"):
                iyi += 1
        yabanci = js("/api/sanat-sil", yontem="POST", govde={"id": gid}, basliklar={"Origin": "http://kotu.example"})[0]
        gecersiz = [js("/api/sanat-sil", yontem="POST", govde={"id": x})[0] for x in ("..", "../zim", "olmayan-galeri", "")]
        duruyor = galeri() is not None and len(js("/api/kitaplar")[1]) == KITAP_SAYISI
        kurulu = [x["kurulu"] for x in js("/api/durum")[1]["paketler"] if x["id"] == gid]
        return sonuc(iyi == len(g["eserler"]) and iyi >= 1 and yabanci == 403 and gecersiz == [404, 404, 404, 404] and duruyor,
                     "“%s”: %d eser, %d KB; resmi açılan ve künyesi tam olan (ad, sanatçı, kamu malı lisansı, Commons kaynak sayfası): %d; örnek: “%s” — %s — %s; yabancı siteden silme: %s; geçersiz adlarla silme: %s; galeri ve kitaplar duruyor: %s; pakette “kurulu” görünüyor: %s. (Katalogda bu ressam için yaklaşık 5 eser bekleniyordu; eksikse Commons istekleri geri çevirmiştir, yeniden indirince kaldığı yerden sürer.)" % (
                         g["baslik"], len(g["eserler"]), boy // 1024, iyi, g["eserler"][0]["ad"][:30], g["eserler"][0]["sanatci"][:25], g["eserler"][0]["lisans"], yabanci, gecersiz, duruyor, kurulu))


# ---- 0.17: verileri başka bir diske taşıma. Ayrı bir deneme kopyasında yapılır; asıl kütüphaneye dokunulmaz. ----
VT = {}
VT_VAR = istek("/api/veri-tasi")[0] == 200
VT_YOK = "bu sürümde verileri uygulamadan taşıma yok (klasör yolu elle yazılıyor)"


def vt(yol, **kw):
    return js(yol, port=VT["port"], **kw)


def _vt_ac():
    VT["p"] = subprocess.Popen([sys.executable, os.path.join(VT["kok"], "imece.py"), "--port", str(VT["port"]), "--tarayici-acma"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _i in range(80):
        try:
            if istek("/api/durum", port=VT["port"], zaman=2)[0] == 200:
                return True
        except Exception:
            time.sleep(0.25)
    return False


def _vt_kapat():
    try:
        istek("/api/kapat", "POST", {}, port=VT["port"], zaman=5)
        VT["p"].wait(15)
    except Exception:
        VT["p"].kill()
        VT["p"].wait(10)


def _vt_ozetler(kok):
    """Klasördeki her dosyanın SHA-256 özeti: {göreli yol: özet}."""
    out = {}
    for k, _d, ds in os.walk(kok):
        for d in ds:
            with open(os.path.join(k, d), "rb") as f:
                out[os.path.relpath(os.path.join(k, d), kok).replace("\\", "/")] = hashlib.sha256(f.read()).hexdigest()
    return out


def _vt_tasi(hedef):
    kod, r = vt("/api/veri-tasi", yontem="POST", govde={"hedef": hedef})
    if kod != 200:
        return kod, r, {}
    for _i in range(600):
        d = vt("/api/veri-tasi")[1]
        if not d["aktif"]:
            return kod, r, d
        time.sleep(0.2)
    return kod, r, {"hata": "taşıma 2 dakikada bitmedi"}


def _vt_ayar():
    with open(os.path.join(VT["kok"], "ayarlar.json"), encoding="utf-8") as f:
        return json.load(f).get("veri")


@senaryo("Y3", "Verileri başka bir yere taşı: her dosya yeni yerde bire bir aynı, eski yer boşalıyor, ayar değişiyor, kitap yeni yerinden açılıyor; uygun olmayan hedefler reddediliyor")
def _():
    if not VT_VAR:
        return sonuc(False, VT_YOK)
    import shutil
    VT.update(kok=tempfile.mkdtemp(prefix="imece-tasi-"), port=PORT + 11, disk=tempfile.mkdtemp(prefix="imece-disk-"))
    shutil.copy(os.path.join(A.klasor, "imece.py"), VT["kok"])
    shutil.copytree(os.path.join(A.klasor, "uygulama"), os.path.join(VT["kok"], "uygulama"))
    os.makedirs(os.path.join(VT["kok"], "veri", "zim"))
    os.makedirs(os.path.join(VT["kok"], "veri", "muzik"))
    shutil.copy(zim_yolu(EK_KUCUK), os.path.join(VT["kok"], "veri", "zim"))
    with open(os.path.join(VT["kok"], "veri", "muzik", "deneme.ogg"), "wb") as f:
        f.write(os.urandom(300000))
    if not _vt_ac():
        return sonuc(False, "deneme kopyası başlatılamadı")
    kid = vt("/api/kitaplar")[1][0]["id"]
    vt("/api/not", yontem="POST", govde={"kitap": kid, "yol": "A/deneme", "baslik": "Deneme", "metin": "taşınınca da durmalı"})
    for _i in range(240):  # başlık ve tam metin dizinleri hazır olsun: onlar da taşınmalı
        o = vt("/api/kitap?k=" + q(kid))[1]
        if o["dizin"]["durum"] == "hazir" and o["tam_metin"].get("durum") in ("hazir", "kapali", "yok"):
            break
        time.sleep(0.5)
    eski_yer = os.path.join(VT["kok"], "veri")
    once = _vt_ozetler(eski_yer)
    yabanci = vt("/api/veri-tasi", yontem="POST", govde={"hedef": VT["disk"]}, basliklar={"Origin": "http://kotu.example"})[0]
    yok = vt("/api/veri-tasi", yontem="POST", govde={"hedef": os.path.join(VT["disk"], "olmayan-disk")})
    dolu = os.path.join(VT["disk"], "dolu")  # içinde başka birinin "Imece-veri" klasörü olan disk
    os.makedirs(os.path.join(dolu, "Imece-veri", "zim"))
    with open(os.path.join(dolu, "Imece-veri", "zim", "baskasinin.zim"), "wb") as f:
        f.write(b"dokunma")
    dolu_r = vt("/api/veri-tasi", yontem="POST", govde={"hedef": dolu})
    dokunulmadi = _vt_ozetler(eski_yer) == once and open(os.path.join(dolu, "Imece-veri", "zim", "baskasinin.zim"), "rb").read() == b"dokunma"
    hedef = os.path.join(VT["disk"], "D")
    os.makedirs(hedef)
    kod, r, son = _vt_tasi(hedef)
    yeni_yer = os.path.join(hedef, "Imece-veri")
    VT["yeni"] = yeni_yer
    sonra = _vt_ozetler(yeni_yer) if os.path.isdir(yeni_yer) else {}
    eski_kalan = [x for x in _vt_ozetler(eski_yer)] if os.path.isdir(eski_yer) else []
    d = vt("/api/durum")[1]
    kitaplar = [k["id"] for k in vt("/api/kitaplar")[1]]
    yol = vt("/api/rastgele?k=" + q(kid))[1].get("yol")
    sayfa = istek("/zim/%s/%s" % (q(kid), yolq(yol)), port=VT["port"])[0] if yol else 0
    nt = vt("/api/not?k=%s&yol=%s" % (q(kid), q("A/deneme")))[1].get("metin")
    ara = vt("/api/kitap?k=" + q(kid))[1]["dizin"]["durum"]
    ayni_yere = vt("/api/veri-tasi", yontem="POST", govde={"hedef": hedef})
    VT["once"] = once
    tamam = (yabanci == 403 and yok[0] == 409 and dolu_r[0] == 409 and dokunulmadi and kod == 200 and not son.get("hata")
             and sonra == once and not eski_kalan and os.path.normcase(_vt_ayar()) == os.path.normcase(yeni_yer)
             and os.path.normcase(d["veri"]) == os.path.normcase(yeni_yer) and d["veri_varsayilan"] is False
             and kitaplar == [kid] and sayfa == 200 and nt == "taşınınca da durmalı" and ayni_yere[0] == 409)
    return sonuc(tamam, "yabancı siteden istek: %s; olmayan disk: %s “%s”; içinde başkasının “Imece-veri” klasörü olan disk: %s “%s”, iki tarafa da dokunulmadı: %s; taşıma: %s “%s”; %d dosyanın %d tanesi yeni yerde özetiyle aynı (kitap, müzik, dizinler, notlar: %s); eski yerde kalan dosya: %s; ayar ve durum yeni yeri gösteriyor: %s; kitap listede: %s, rastgele bir sayfası %s, notu duruyor: %s, başlık dizini: %s; aynı yere ikinci kez: %s “%s”" % (
        yabanci, yok[0], (yok[1] or {}).get("hata", "")[:40], dolu_r[0], (dolu_r[1] or {}).get("hata", "")[:50], dokunulmadi, kod, son.get("hata") or son.get("mesaj", "")[:60],
        len(once), len([x for x in once if sonra.get(x) == once[x]]), ", ".join(sorted({x.split("/")[0] for x in once})), eski_kalan or "yok",
        os.path.normcase(str(_vt_ayar())) == os.path.normcase(yeni_yer) and os.path.normcase(d["veri"]) == os.path.normcase(yeni_yer),
        kitaplar == [kid], sayfa, nt == "taşınınca da durmalı", ara, ayni_yere[0], (ayni_yere[1] or {}).get("hata", "")[:40]))


@senaryo("Y4", "Verilerin durduğu disk takılı değilken: İmece yine açılıyor, kütüphane boş ve nedeni söyleniyor, ayar bozulmuyor; disk geri gelince kitaplar geri geliyor")
def _():
    if "yeni" not in VT:
        return sonuc(False, VT_YOK if not VT_VAR else "Y3 çalışmadı")
    import string
    _vt_kapat()
    # "Takılı olmayan disk": bu bilgisayarda bulunmayan bir sürücü harfi (Windows) ya da oluşturulamayan bir kök yol.
    if os.name == "nt":
        harf = next(h for h in reversed(string.ascii_uppercase) if not os.path.exists(h + ":\\"))
        olmayan = harf + ":\\Imece-veri"
    else:
        olmayan = "/proc/olmayan-disk/Imece-veri"
    ayar = os.path.join(VT["kok"], "ayarlar.json")
    with open(ayar, encoding="utf-8") as f:
        a = json.load(f)
    gercek = a["veri"]
    a["veri"] = olmayan
    with open(ayar, "w", encoding="utf-8") as f:
        json.dump(a, f)
    acildi = _vt_ac()
    d = vt("/api/durum")[1] if acildi else {}
    n0 = len(vt("/api/kitaplar")[1]) if acildi else -1
    tasima = vt("/api/veri-tasi", yontem="POST", govde={"hedef": VT["disk"]}) if acildi else (0, {})
    sayfa = istek("/uygulama/index.html", port=VT["port"])[2].decode("utf-8") if acildi else ""
    ayar_duruyor = _vt_ayar() == olmayan
    yeni_yerde = _vt_ozetler(VT["yeni"]) == VT["once"]
    _vt_kapat()
    a["veri"] = gercek  # disk geri takıldı
    with open(ayar, "w", encoding="utf-8") as f:
        json.dump(a, f)
    acildi2 = _vt_ac()
    d2 = vt("/api/durum")[1] if acildi2 else {}
    n1 = len(vt("/api/kitaplar")[1]) if acildi2 else -1
    tamam = (acildi and d.get("veri_yok") is True and d.get("veri_yok_yol") == olmayan and n0 == 0 and tasima[0] == 409 and ayar_duruyor
             and yeni_yerde and "Kitapların durduğu disk takılı değil" in sayfa and acildi2 and d2.get("veri_yok") is False and n1 == 1)
    return sonuc(tamam, "ayar “%s” iken açıldı: %s; durum “disk yok” diyor: %s (yol: %s); kütüphanede %d kitap; taşıma isteği: %s “%s”; ayar dosyası değişmedi: %s; öbür diskteki dosyalara dokunulmadı: %s; arayüzde uyarı metni var: %s; disk geri gelince açıldı: %s, “disk yok”: %s, kitap: %d. (Disk gerçekten sökülmedi; olmayan bir sürücü harfiyle denendi.)" % (
        olmayan, acildi, d.get("veri_yok"), d.get("veri_yok_yol"), n0, tasima[0], (tasima[1] or {}).get("hata", "")[:50], ayar_duruyor, yeni_yerde,
        "Kitapların durduğu disk takılı değil" in sayfa, acildi2, d2.get("veri_yok"), n1))


@senaryo("Y5", "Verileri İmece klasörüne geri al: dosyalar bire bir aynı geri geliyor, öbür diskteki klasör kalkıyor; yarıda kalmış bir kopyanın üstüne yeniden taşınabiliyor")
def _():
    if "yeni" not in VT:
        return sonuc(False, VT_YOK if not VT_VAR else "Y3 çalışmadı")
    import shutil
    try:
        # Taşıma birkaç saniye sürsün diye araya büyük bir dosya konur; sürerken yazma işlemleri reddedilmeli.
        with open(os.path.join(VT["yeni"], "muzik", "buyuk.ogg"), "wb") as f:
            for _i in range(75):
                f.write(os.urandom(4 * 1024 * 1024))
        VT["once"] = _vt_ozetler(VT["yeni"])
        kid = vt("/api/kitaplar")[1][0]["id"]
        kod, r = vt("/api/veri-tasi", yontem="POST", govde={"hedef": ""})
        surerken = {"not": None, "ikinci": None, "kitap": None, "yuzde": None}
        son = {"hata": "taşıma 3 dakikada bitmedi"}
        for _i in range(1800):
            d = vt("/api/veri-tasi")[1]
            if not d["aktif"]:
                son = d
                break
            if surerken["not"] is None:
                surerken["yuzde"] = d["yuzde"]
                surerken["not"] = vt("/api/not", yontem="POST", govde={"kitap": kid, "yol": "A/x", "baslik": "x", "metin": "taşınırken yazılmamalı"})[0]
                surerken["ikinci"] = vt("/api/veri-tasi", yontem="POST", govde={"hedef": VT["disk"]})[0]
                surerken["kitap"] = len(vt("/api/kitaplar")[1])
            time.sleep(0.1)
        eski_yer = os.path.join(VT["kok"], "veri")
        geri = _vt_ozetler(eski_yer)
        geri_n, geri_ayni = len(VT["once"]), len([x for x in VT["once"] if geri.get(x) == VT["once"][x]])
        geri_tam = geri == VT["once"]
        yazilmadi =vt("/api/not?k=%s&yol=%s" % (q(kid), q("A/x")))[1].get("metin") == ""
        kalkti = not os.path.exists(VT["yeni"])
        d = vt("/api/durum")[1]
        n = len(vt("/api/kitaplar")[1])
        ayar1 = _vt_ayar()
        os.remove(os.path.join(eski_yer, "muzik", "buyuk.ogg"))  # ikinci taşıma küçük kalsın
        VT["once"] = _vt_ozetler(eski_yer)
        # Yarıda kalmış taşıma: hedefte işaretli, eksik bir kopya var. Yeniden taşıma onun üstüne yazabilmeli.
        yarim = os.path.join(VT["disk"], "Y")
        os.makedirs(os.path.join(yarim, "Imece-veri", "zim"))
        with open(os.path.join(yarim, "Imece-veri", ".tasiniyor"), "w") as f:
            f.write("tasiniyor")
        with open(os.path.join(yarim, "Imece-veri", "zim", os.path.basename(zim_yolu(EK_KUCUK))), "wb") as f:
            f.write(b"yarim kalmis kopya")
        kod2, r2, son2 = _vt_tasi(yarim)
        ustune = _vt_ozetler(os.path.join(yarim, "Imece-veri")) == VT["once"]
        n2 = len(vt("/api/kitaplar")[1])
        tamam = (kod == 200 and not son.get("hata") and geri_tam and kalkti and d["veri_varsayilan"] is True and ayar1 == "veri" and n == 1
                 and kod2 == 200 and not son2.get("hata") and ustune and n2 == 1
                 and surerken["not"] == 409 and surerken["ikinci"] == 409 and surerken["kitap"] == 0 and yazilmadi)
        return sonuc(tamam, "taşıma sürerken (%%%s iken): not yazma isteği %s, ikinci taşıma isteği %s, açık kitap %s; o not sonradan da yok: %s; geri alma (300 MB'lık ek dosyayla): %s “%s”; " % (
            surerken["yuzde"], surerken["not"], surerken["ikinci"], surerken["kitap"], yazilmadi, kod, (son.get("hata") or son.get("mesaj", ""))[:50]) + "geri alma: %s “%s”;%d dosyanın %d tanesi özetiyle aynı; öbür diskteki klasör kalktı: %s; ayar “%s”, durum İmece klasörünü gösteriyor: %s; kitap: %d; yarım kalmış (işaretli) kopyanın üstüne taşıma: %s “%s”, dosyalar tam ve aynı (işaret dosyası kalmadı): %s, kitap: %d" % (
            kod, son.get("hata") or son.get("mesaj", "")[:50], geri_n, geri_ayni, kalkti, ayar1,
            d["veri_varsayilan"], n, kod2, son2.get("hata") or son2.get("mesaj", "")[:40], ustune, n2))
    finally:
        _vt_kapat()
        shutil.rmtree(VT["kok"], ignore_errors=True)
        shutil.rmtree(VT["disk"], ignore_errors=True)


@senaryo("Y2", "Flash diske kur (içeriksiz): uygulama eksiksiz kopyalanıyor ve kopya çalışıyor")
def _():
    import filecmp, shutil
    gecici = tempfile.mkdtemp(prefix="imece-flash-")
    try:
        kod, r = js("/api/flash", yontem="POST", govde={"hedef": gecici, "icerik": False})
        for _i in range(60):
            d = js("/api/flash")[1]
            if not d["aktif"]:
                break
            time.sleep(0.5)
        farkli = []
        for kok, _d, ds in os.walk(os.path.join(A.klasor, "uygulama")):
            for dd in ds:
                if "__pycache__" in kok:
                    continue
                k = os.path.join(kok, dd)
                h = os.path.join(gecici, "Imece", "uygulama", os.path.relpath(k, os.path.join(A.klasor, "uygulama")))
                if not os.path.exists(h) or not filecmp.cmp(k, h, shallow=False):
                    farkli.append(dd)
        ana = filecmp.cmp(os.path.join(A.klasor, "imece.py"), os.path.join(gecici, "Imece", "imece.py"), shallow=False)
        acilis = [d for d in os.listdir(os.path.join(gecici, "Imece")) if d.lower().endswith((".bat", ".txt"))]
        p = subprocess.Popen([sys.executable, os.path.join(gecici, "Imece", "imece.py"), "--port", str(PORT + 2), "--tarayici-acma"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        calisti = False
        try:
            for _i in range(40):
                try:
                    calisti = istek("/api/durum", port=PORT + 2, zaman=2)[0] == 200
                    break
                except Exception:
                    time.sleep(0.25)
        finally:
            p.terminate()
            p.wait(10)
        return sonuc(ana and not farkli and calisti and acilis, "%s | imece.py aynı: %s | farklı/eksik dosya: %s | kopya çalıştı: %s | açma dosyası/beni oku: %s" % (
            d["mesaj"][:40], ana, farkli or "yok", calisti, acilis or "YOK (flash'ta neye tıklanacağı belli değil)"))
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


# ================================================================ R. REHBER
@senaryo("R1", "Kanama rehberi karar ağacı: kopuk dal yok, her yol bir sona varıyor")
def _():
    t = open(os.path.join(A.klasor, "uygulama", "rehberler", "kanama.js"), encoding="utf-8").read()
    R = json.loads(t[t.index("{", t.index("window.REHBER")):t.rindex("}") + 1])
    D = R["dugumler"]
    kopuk = [(k, s["git"]) for k, d in D.items() for s in d.get("secenekler", []) if s["git"] not in D]
    cikmaz = [k for k, d in D.items() if not d.get("son") and not d.get("secenekler")]
    gorulen, sira = set(), [R["baslangic"]]
    while sira:
        k = sira.pop()
        if k in gorulen or k not in D:
            continue
        gorulen.add(k)
        sira += [s["git"] for s in D[k].get("secenekler", [])]
    yetim = [k for k in D if k not in gorulen]
    sessiz = [k for k, d in D.items() if not (d.get("ses") or d.get("metin"))]
    kaynaksiz = [k for k, d in D.items() if not d.get("kn")]
    # 0.15'e kadar duran, doğrulanmamış "Kızılay / ERC / AHA ile uyumlu" satırı geri gelmemeli
    return sonuc(not kopuk and not cikmaz and not yetim and not sessiz and not kaynaksiz and "uyumlu yazılmıştır" not in t,
                 "%d düğüm, %d bitiş; kopuk bağlantı %s, çıkmaz %s, ulaşılamayan %s, sesi olmayan %s, kaynak numarası olmayan %s; doğrulanmamış 'uyumlu' satırı: %s" % (
                     len(D), len([1 for d in D.values() if d.get("son")]), kopuk or "yok", cikmaz or "yok", yetim or "yok", sessiz or "yok",
                     kaynaksiz or "yok", "VAR" if "uyumlu yazılmıştır" in t else "yok"))


# ================================================================ İ. İNDİRME (internet ister)
if A.indirme:
    @senaryo("İ1", "Katalog internetten geliyor")
    def _():
        kod, l = js("/api/katalog?dil=tur")
        return sonuc(kod == 200 and len(l) > 50, "%d Türkçe içerik" % len(l))

    @senaryo("İ2", "Duraklat: sıradaki paketler kaybolmuyor; Devam: kaldığı yerden sürüyor")
    def _():
        kod, l = js("/api/katalog?dil=tur")
        aday = [x for x in l if not x["kurulu"] and x["boyut_mb"] and 20 <= x["boyut_mb"] <= 60 and "wikipedia_tr" in x["ad"]][:2]
        if len(aday) < 2:
            return "ATLANDI", "İndirilecek uygun iki küçük paket kalmadı."
        js("/api/indir", yontem="POST", govde={"katalog": [x["id"] for x in aday]})
        yarim = os.path.join(VERI, "zim", aday[0]["dosya"] + ".yarim")
        for _i in range(100):
            if os.path.exists(yarim) and os.path.getsize(yarim) > 2 * 1024 * 1024:
                break
            time.sleep(0.2)
        js("/api/durdur", yontem="POST", govde={})
        time.sleep(3)
        d = js("/api/durum")[1]["is"]
        boy = os.path.getsize(yarim) if os.path.exists(yarim) else 0
        bekleyen = d.get("bekleyen", d.get("kuyruk", []))
        korundu = len(bekleyen) >= 2
        if "bekleyen" in d:
            js("/api/devam", yontem="POST", govde={})
        else:
            js("/api/indir", yontem="POST", govde={"katalog": [aday[0]["id"]]})
        for _i in range(600):
            if not js("/api/durum")[1]["is"]["aktif"]:
                break
            time.sleep(1)
        son = os.path.join(VERI, "zim", aday[0]["dosya"])
        tam = os.path.exists(son) and round(os.path.getsize(son) / 1048576) == aday[0]["boyut_mb"]
        ikinci = os.path.exists(os.path.join(VERI, "zim", aday[1]["dosya"]))
        try:
            Z(son).maddeler()
            saglam = True
        except Exception as e:
            saglam = False
        return sonuc(korundu and tam and saglam and ikinci and boy > 0,
                     "duraklatınca yarım dosya %d MB; sırada bekleyen %d paket (%s); devamdan sonra ilk paket tam: %s, açılıyor: %s; ikinci paket de indi: %s" % (
                         boy // 1048576, len(bekleyen), "korundu" if korundu else "KAYBOLDU", tam, saglam, ikinci))


gecti = len([s for s in SONUC if s["durum"] == "GEÇTİ"])
kaldi = len([s for s in SONUC if s["durum"] == "KALDI"])
print("\nİmece %s: %d senaryo, %d geçti, %d kaldı, %d atlandı" % (SURUM, len(SONUC), gecti, kaldi, len(SONUC) - gecti - kaldi))
if A.json:
    with open(A.json, "w", encoding="utf-8") as f:
        json.dump({"surum": SURUM, "sonuc": SONUC}, f, ensure_ascii=False, indent=1)
