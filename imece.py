#!/usr/bin/env python3
"""İmece — çevrimdışı bilgi ve afet hazırlık uygulaması.

Windows'ta Imece-Ac.bat'a çift tıkla: klasördeki hazır Python (python/ klasörü) ile, siyah pencere
açılmadan çalışır ve uygulama tarayıcıda açılır. Kapatmak için uygulamadaki "İmece'yi kapat" düğmesi.
Komut satırı seçenekleri (geliştirici / Raspberry Pi):
  python imece.py --ag        aynı ağdaki telefonlar da bağlanabilsin (Pi kutusu modu)
  python imece.py --port 8642 --tarayici-acma
Sadece Python standart kütüphanesi (3.9+). Zstd sıkıştırmalı paketler için Python 3.14+
ya da "pip install zstandard" gerekir (klasördeki hazır Python 3.14'tür).
"""
import argparse, bisect, hashlib, html as _html, json, lzma, mimetypes, os, queue, random, re, shutil, socket, string, struct, sys, tempfile, threading, time
import traceback, unicodedata, urllib.parse, urllib.request, webbrowser
import xml.etree.ElementTree as ET
from array import array
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SURUM = "0.19"
if getattr(sys, "frozen", False):
    KOK = os.path.dirname(sys.executable)
else:
    KOK = os.path.dirname(os.path.abspath(__file__))
UYG = os.path.join(KOK, "uygulama")
AYAR_DOSYA = os.path.join(KOK, "ayarlar.json")
# Projenin herkese açık adresi (örneğin GitHub deposu). Wikimedia gibi kaynaklar, kendini ve iletişim adresini
# bildirmeyen istemcileri kısıtlıyor; depo açılınca adresi buraya yazılmalı. Boşken yalnızca ad ve sürüm gönderilir.
PROJE_ADRESI = "https://github.com/vesso-go/imece"
UA = {"User-Agent": "Imece/" + SURUM + (" (+%s)" % PROJE_ADRESI if PROJE_ADRESI else "")}
MB = 1024 * 1024
# Klasörün içindeki hazır Python (python.org'un resmi, değiştirilmemiş "embeddable" paketi).
GOMULU_PY = os.path.join(KOK, "python")
GOMULU = os.path.normcase(os.path.dirname(os.path.abspath(sys.executable))) == os.path.normcase(GOMULU_PY)
# pythonw ile (siyah pencere olmadan) çalışırken yazılacak bir ekran yoktur.
PENCERESIZ = (sys.stdout is None or sys.stderr is None
              or os.path.basename(sys.executable).lower().startswith("pythonw"))
GUNLUK = ""


def gunluk_ac():
    """Penceresiz çalışırken çıktılar bir günlük dosyasına yazılır (sorun olursa bakılacak yer)."""
    global GUNLUK
    for yol in (os.path.join(KOK, "imece-gunluk.log"), os.path.join(tempfile.gettempdir(), "imece-gunluk.log")):
        try:
            f = open(yol, "w", encoding="utf-8", errors="replace", buffering=1)
        except OSError:
            continue
        sys.stdout = sys.stderr = f
        GUNLUK = yol
        return
    sys.stdout = sys.stderr = open(os.devnull, "w")


def hata_goster(metin):
    """Açılış hatasını kullanıcıya gösterir: pencere yoksa Windows ileti kutusuyla."""
    print(metin, flush=True)
    if PENCERESIZ and os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, metin, "İmece", 0x10 | 0x10000)  # hata simgesi, öne getir
        except Exception:
            pass

try:  # Python 3.14+
    from compression import zstd as _zstd

    def zstd_ac(b):
        return _zstd.decompress(b)
except Exception:
    try:
        import zstandard as _zs

        def zstd_ac(b):
            return _zs.ZstdDecompressor().decompressobj().decompress(b)
    except Exception:
        zstd_ac = None


# =====================================================================
#  AYARLAR
# =====================================================================
def ayar_oku():
    a = {"veri": "veri"}
    try:
        with open(AYAR_DOSYA, encoding="utf-8") as f:
            a.update(json.load(f))
    except Exception:
        pass
    return a


def ayar_yaz(a):
    with open(AYAR_DOSYA, "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False, indent=1)


VERI_YOK = [None]  # ayarlardaki veri klasörüne ulaşılamıyorsa (diski takılı değil) o klasörün yolu


def veri_dir():
    v = ayar_oku()["veri"]
    v = v if os.path.isabs(v) else os.path.join(KOK, v)
    try:
        os.makedirs(os.path.join(v, "zim"), exist_ok=True)
        os.makedirs(os.path.join(v, "muzik"), exist_ok=True)
        VERI_YOK[0] = None
        return v
    except OSError:
        # Veriler başka bir diske taşınmışsa ve o disk takılı değilse İmece yine açılsın: İmece klasöründeki
        # (boş) veri klasörü kullanılır, ayar değiştirilmez. Disk takılınca kitaplar kendiliğinden geri gelir.
        VERI_YOK[0] = v
        y = os.path.join(KOK, "veri")
        os.makedirs(os.path.join(y, "zim"), exist_ok=True)
        os.makedirs(os.path.join(y, "muzik"), exist_ok=True)
        return y


# =====================================================================
#  TÜRKÇE SIRALAMA VE ARAMA YARDIMCILARI
# =====================================================================
_ALF = "abcçdefgğhıijklmnoöpqrsştuüvwxyz"
# A–Z kovaları: Türk alfabesi + Q, W, X (yabancı adlar) + rakamlar + geri kalan her şey.
HARFLER = list("ABCÇDEFGĞHIİJKLMNOÖPQRSŞTUÜVWXYZ") + ["0-9", "#"]
# Sıralama: her harf alfabedeki sırasına göre tek baytlık bir işarete çevrilir (ç, c'den hemen sonra gelir).
_SIRA_TABLO = {ord(c): chr(0x41 + i) for i, c in enumerate(_ALF)}
_SIRA_TABLO.update({ord(c): "!" for c in "[\\]^_`"})
_DUZ_TABLO = str.maketrans("çğıöşü", "cgiosu")
_BAS_SUS = " \t\"'‘’“”«»‹›([{<-–—.,:;!?¿¡*#/\\_~`´^&%$+=|@"


_TR_OZEL = frozenset("çğıöşü")


def tr_kucuk(s):
    """Türkçe küçük harf (I → ı, İ → i). Türk alfabesinde olmayan aksanlı harfler yalın haline iner
    (é → e, ñ → n, â → a): 'Alfréd' sıralamada ve aramada 'Alfred' gibi davranır. Harf sayısı değişmez."""
    s = s.replace("I", "ı").replace("İ", "i").lower()
    if s.isascii():
        return s
    out = []
    for ch in s:
        if ch >= "\x80" and ch not in _TR_OZEL:
            taban = unicodedata.normalize("NFD", ch)[0]
            if taban.isascii() and taban.isalpha():
                ch = taban
        out.append(ch)
    return "".join(out)


def duz(s):
    """Arama için sadeleştirme: küçük harf + noktasız, şapkasız (ısı = isi, şiir = siir)."""
    return tr_kucuk(s).translate(_DUZ_TABLO)


def sira_parcasi(baslik):
    """(kova numarası, sıralama anahtarı). Baştaki tırnak, parantez gibi işaretler yok sayılır."""
    t = tr_kucuk(baslik)
    c = t.lstrip(_BAS_SUS) or t
    ilk = c[:1]
    p = _ALF.find(ilk) if ilk else -1
    if p >= 0:
        kova = p
    elif ilk and ilk in "0123456789":
        kova = 32
    else:
        kova = 33
    return kova, c.translate(_SIRA_TABLO)


# =====================================================================
#  ZIM OKUYUCU (kendi yazdığımız; açık ZIM biçim tarifine göre)
# =====================================================================
class ZimHata(Exception):
    pass


class Zim:
    BUYU = 72173914

    def __init__(self, yol):
        self.yol = yol
        self.f = open(yol, "rb")
        self.kilit = threading.Lock()
        h = self._oku(0, 80)
        buyu, self.ana, self.alt = struct.unpack_from("<IHH", h, 0)
        if buyu != self.BUYU:
            raise ZimHata("ZIM dosyası değil")
        # Paketin kimliği: dosya kopyalansa da değişmez (dizin önbelleği bununla eşleşir).
        self.imza = "%s-%d" % (h[8:24].hex(), os.path.getsize(yol))
        (self.n, self.kume_n, self.url_ptr, self.baslik_ptr, self.kume_ptr,
         self.mime_ptr, self.ana_sayfa, _, self.sagla_ptr) = struct.unpack_from("<IIQQQQIIQ", h, 24)
        ham = self._oku(self.mime_ptr, min(65536, self.url_ptr - self.mime_ptr))
        self.mimeler = []
        for p in ham.split(b"\0"):
            if not p:
                break
            self.mimeler.append(p.decode("utf-8", "replace"))
        self.kume_onbellek = OrderedDict()
        self.giris_onbellek = OrderedDict()
        self.yeni_ad_alani = (self.ana, self.alt) >= (6, 1)
        self.makale_ns = "C" if self.yeni_ad_alani else "A"
        self._meta = None

    def _oku(self, konum, boy):
        with self.kilit:
            self.f.seek(konum)
            return self.f.read(boy)

    def kapat(self):
        self.f.close()

    # --- dizin girdileri ---
    def giris(self, i):
        i &= 0x7FFFFFFF
        g = self.giris_onbellek.get(i)
        if g:
            return g
        konum = struct.unpack("<Q", self._oku(self.url_ptr + 8 * i, 8))[0]
        ham = self._oku(konum, 2048)
        mime, plen, ns = struct.unpack_from("<HBc", ham, 0)
        if mime == 0xFFFF:
            hedef = struct.unpack_from("<I", ham, 8)[0]
            bas = 12
            g = {"yonlendirme": hedef}
        else:
            kume, blob = struct.unpack_from("<II", ham, 8)
            bas = 16
            g = {"kume": kume, "blob": blob}
        son = ham.find(b"\0", bas)
        while son < 0:  # çok uzun adres
            ham += self._oku(konum + len(ham), 4096)
            son = ham.find(b"\0", bas)
        url = ham[bas:son]
        son2 = ham.find(b"\0", son + 1)
        while son2 < 0:
            ham += self._oku(konum + len(ham), 4096)
            son2 = ham.find(b"\0", son + 1)
        baslik = ham[son + 1:son2]
        g.update({"i": i, "mime": mime, "ns": ns.decode("latin-1"), "url": url.decode("utf-8", "replace"),
                  "baslik": baslik.decode("utf-8", "replace") or url.decode("utf-8", "replace")})
        self.giris_onbellek[i] = g
        if len(self.giris_onbellek) > 4096:
            try:
                self.giris_onbellek.popitem(last=False)
            except KeyError:
                pass
        return g

    def mime_adi(self, g):
        m = g.get("mime", 0)
        return self.mimeler[m] if m < len(self.mimeler) else "application/octet-stream"

    def find(self, ns, url):
        """(ad alanı, adres) ile ikili arama; girdi indeksini döner."""
        hedef = (ns, url)
        lo, hi = 0, self.n
        while lo < hi:
            orta = (lo + hi) // 2
            g = self.giris(orta)
            anahtar = (g["ns"], g["url"])
            if anahtar < hedef:
                lo = orta + 1
            elif anahtar > hedef:
                hi = orta
            else:
                return orta
        return None

    def coz(self, i, derinlik=0):
        g = self.giris(i)
        if "yonlendirme" in g and derinlik < 20:
            return self.coz(g["yonlendirme"], derinlik + 1)
        return g

    # --- kümeler (sıkıştırılmış veri blokları) ---
    def kume(self, k):
        v = self.kume_onbellek.get(k)
        if v is not None:
            try:
                self.kume_onbellek.move_to_end(k)
            except KeyError:  # başka bir istek tam o anda önbellekten atmış olabilir
                pass
            return v
        bas = struct.unpack("<Q", self._oku(self.kume_ptr + 8 * k, 8))[0]
        if k + 1 < self.kume_n:
            son = struct.unpack("<Q", self._oku(self.kume_ptr + 8 * (k + 1), 8))[0]
        else:
            son = self.sagla_ptr
        ham = self._oku(bas, son - bas)
        bilgi = ham[0]
        sik, genis = bilgi & 0x0F, bilgi & 0x10
        veri = ham[1:]
        if sik in (0, 1):
            pass
        elif sik == 4:
            d = lzma.LZMADecompressor()
            veri = d.decompress(veri)
        elif sik == 5:
            if zstd_ac is None:
                raise ZimHata("Bu paket zstd ile sıkıştırılmış. Python 3.14'e güncelle ya da 'pip install zstandard' çalıştır.")
            veri = zstd_ac(veri)
        else:
            raise ZimHata("Desteklenmeyen sıkıştırma: %d" % sik)
        osz = 8 if genis else 4
        fmt = "<Q" if genis else "<I"
        ilk = struct.unpack_from(fmt, veri, 0)[0]
        adet = ilk // osz
        ofsetler = [struct.unpack_from(fmt, veri, osz * j)[0] for j in range(adet)]
        v = (veri, ofsetler)
        self.kume_onbellek[k] = v
        if len(self.kume_onbellek) > 6:
            try:
                self.kume_onbellek.popitem(last=False)
            except KeyError:
                pass
        return v

    def icerik(self, g):
        veri, of = self.kume(g["kume"])
        b = g["blob"]
        return veri[of[b]:of[b + 1]]

    # --- yardımcılar ---
    def ana_sayfa_url(self):
        if self.ana_sayfa != 0xFFFFFFFF and self.ana_sayfa < self.n:
            g = self.coz(self.ana_sayfa)
            return g["ns"] + "/" + g["url"]
        i = self.find("W", "mainPage")
        if i is not None:
            g = self.coz(i)
            return g["ns"] + "/" + g["url"]
        return None

    def meta(self):
        if self._meta is None:
            m = {}
            for k in ("Title", "Description", "LongDescription", "Language", "Creator", "Date", "Publisher",
                      "License", "Source", "Flavour", "Name", "Counter"):
                i = self.find("M", k)
                if i is not None:
                    try:
                        m[k] = self.icerik(self.coz(i)).decode("utf-8", "replace").strip()
                    except Exception:
                        pass
            self._meta = m
        return self._meta

    def simge_url(self):
        for ad in ("Illustration_48x48@1", "Illustration_96x96@2"):
            if self.find("M", ad) is not None:
                return "M/" + ad
        return None

    def madde_tahmini(self):
        """Paketin kendi sayacına göre madde sayısı (dizin hazır değilken gösterilir)."""
        n = 0
        for p in self.meta().get("Counter", "").split(";"):
            ad, _, adet = p.rpartition("=")
            if ad.strip().startswith("text/html") and adet.strip().isdigit():
                n += int(adet)
        return n or self.baslik_dizini()[1]

    def baslik_dizini(self):
        """Başlık sırası. Yeni paketlerde başlıktaki gösterici kaldırıldı;
        dizin X/listing/titleOrdered/v1 (ön makaleler) ya da v0 içinde durur."""
        if getattr(self, "_bd", None) is not None:
            return self._bd
        boy = os.path.getsize(self.yol)
        sonuc = None
        self.liste_tam = False  # True: liste sadece makalelerden oluşuyor (v1)
        for ad in ("listing/titleOrdered/v1", "listing/titleOrdered/v0"):
            i = self.find("X", ad)
            if i is not None:
                b = self.icerik(self.coz(i))
                sonuc = (b, len(b) // 4)
                self.liste_tam = ad.endswith("v1")
                break
        if sonuc is None:
            if self.baslik_ptr and self.baslik_ptr + 4 * self.n <= boy:
                sonuc = (None, self.n)
            else:
                sonuc = (b"", 0)
        self._bd = sonuc
        return sonuc

    def _baslik_giris(self, j):
        dizin, _ = self.baslik_dizini()
        if dizin is None:
            idx = struct.unpack("<I", self._oku(self.baslik_ptr + 4 * j, 4))[0]
        else:
            idx = struct.unpack_from("<I", dizin, 4 * j)[0]
        return self.giris(idx)

    # --- sade kip: bellekteki başlık dizini yokken (çok büyük kitap ya da dizin kurulurken) ---
    def _sinir(self, metin):
        """Başlık listesinde (ad alanı, başlık) >= (makale alanı, metin) olan ilk konum."""
        ns = self.makale_ns
        _, n = self.baslik_dizini()
        lo, hi = 0, n
        while lo < hi:
            orta = (lo + hi) // 2
            g = self._baslik_giris(orta)
            if (g["ns"], g["baslik"]) < (ns, metin):
                lo = orta + 1
            else:
                hi = orta
        return lo

    def sade_aralik(self, harf):
        """Harfin başlık listesindeki aralıkları (büyük ve küçük harfle başlayanlar)."""
        on = self.__dict__.setdefault("_aralik", {})
        if harf not in on:
            if harf == "#":
                r = []
            elif harf == "0-9":
                r = [(self._sinir("0"), self._sinir(":"))]
            else:
                r = [(self._sinir(x), self._sinir(x + "\U0010ffff")) for x in dict.fromkeys((harf, tr_kucuk(harf)))]
            on[harf] = [(a, b) for a, b in r if b > a]
        return on[harf]

    def sade_dizin(self, harf, bas=0, adet=200):
        """Sade kipte harf listesi. Dosyadaki sırayla gelir (Türkçe sıralı değildir), yönlendirmeleri de içerir."""
        sonuc, atla, toplam = [], bas, 0
        araliklar = self.sade_aralik(harf)
        toplam = sum(b - a for a, b in araliklar)
        tuketilen = bas
        for a, b in araliklar:
            if atla >= b - a:
                atla -= b - a
                continue
            j = a + atla
            atla = 0
            while j < b and len(sonuc) < adet:
                g = self._baslik_giris(j)
                j += 1
                tuketilen += 1
                h = self.coz(g["i"])
                if h.get("mime") is None or "html" not in self.mime_adi(h):
                    continue
                sonuc.append({"baslik": g["baslik"], "yol": h["ns"] + "/" + h["url"]})
            if len(sonuc) >= adet:
                break
        return sonuc, (tuketilen if tuketilen < toplam else None), toplam

    def rastgele(self):
        _, n = self.baslik_dizini()
        for _ in range(40):
            if not n:
                break
            g = self._baslik_giris(random.randrange(n))
            h = self.coz(g["i"])
            if g["ns"] == self.makale_ns and "html" in self.mime_adi(h):
                return h["ns"] + "/" + h["url"]
        return self.ana_sayfa_url()

    def baslik_ara(self, sorgu, adet=15):
        """Başlık ön ekiyle arama (başlık dizini üzerinden)."""
        sonuc, gorulen = [], set()
        tr_buyuk = {"i": "İ", "ı": "I"}
        s = sorgu.strip()
        if not s:
            return []
        varyant = [s, (tr_buyuk.get(s[0], s[0].upper())) + s[1:], s.lower(), s.title()]
        ns = self.makale_ns
        dizin, adet_n = self.baslik_dizini()

        def tg(j):
            if dizin is None:
                idx = struct.unpack("<I", self._oku(self.baslik_ptr + 4 * j, 4))[0]
            else:
                idx = struct.unpack_from("<I", dizin, 4 * j)[0]
            return self.giris(idx)

        for v in varyant:
            lo, hi = 0, adet_n
            while lo < hi:
                orta = (lo + hi) // 2
                g = tg(orta)
                if (g["ns"], g["baslik"]) < (ns, v):
                    lo = orta + 1
                else:
                    hi = orta
            j = lo
            while j < adet_n and len(sonuc) < adet:
                g = tg(j)
                if g["ns"] != ns or not g["baslik"].startswith(v):
                    break
                hedef = self.coz(g["i"])
                if hedef.get("mime") is not None and "html" in self.mime_adi(hedef) and g["i"] not in gorulen:
                    gorulen.add(g["i"])
                    sonuc.append({"baslik": g["baslik"], "yol": g["ns"] + "/" + g["url"]})
                j += 1
            if len(sonuc) >= adet:
                break
        return sonuc


# =====================================================================
#  BAŞLIK DİZİNİ
#  Bir kitabın bütün başlıkları bellekte: Türk alfabesine göre sıralı ve aranabilir.
#  Kitap giriş ekranı (madde sayısı, A–Z, bölümler) ve arama buradan beslenir.
#  İlk açılışta arka planda kurulur ve veri/dizin/ altına yazılır; sonraki açılışlar anlıktır.
# =====================================================================
class Dizin:
    SURUM = 2  # sıralama ya da dosya düzeni değişince artır: eski dizin dosyaları kendiliğinden yeniden kurulur
    YON = 0x80000000  # girdi numarasının en üst biti: bu başlık bir yönlendirmedir

    def __init__(self):
        self.idx = array("I")  # sıralı konum -> pakette girdi numarası (+ YON biti)
        self.ofs = array("I")  # sıralı konum -> düz metin içindeki başlangıç (n+1 eleman)
        self.mad = array("I")  # yönlendirme olmayanların sıralı konumları (asıl maddeler)
        self.duz = b"\n"       # "\n" + başlıkların sadeleştirilmiş hali, "\n" ile ayrılmış
        self.kova = {}         # harf -> (mad içinde baş, son)
        self.bolum = []        # [{ad, anahtar, adet}] başlıklardan çıkarılan bölümler

    # ---- kurma ----
    @classmethod
    def kur(cls, z, ilerleme=None):
        d = cls()
        ham, n = z.baslik_dizini()
        if not n:
            d.ofs.append(1)
            return d
        if ham is None:
            ham = z._oku(z.baslik_ptr, 4 * n)
        sira = array("I")
        sira.frombytes(ham[:4 * n])
        if sys.byteorder == "big":
            sira.byteswap()
        html = {i for i, m in enumerate(z.mimeler) if "html" in m}
        ns_bayt = ord(z.makale_ns)
        tam = z.liste_tam
        kayit = []
        with open(z.yol, "rb") as f:  # kendi dosya tutamacı: okuyan isteklere takılmaz
            f.seek(z.url_ptr)
            ptr = array("Q")
            ptr.frombytes(f.read(8 * z.n))
            if sys.byteorder == "big":
                ptr.byteswap()
            hedefler = sorted({i for i in sira if i < z.n}, key=ptr.__getitem__)  # dosyadaki sırayla oku
            tampon, tbas, pen = b"", -1, 1 << 20
            for sayac, i in enumerate(hedefler):
                g = ptr[i] - tbas
                if tbas < 0 or g < 0 or len(tampon) - g < 70000:
                    if tbas < 0 or g < 0 or len(tampon) == pen:  # tampon dosya sonuna gelmediyse yenile
                        f.seek(ptr[i])
                        tampon, tbas, g = f.read(pen), ptr[i], 0
                mime = tampon[g] | (tampon[g + 1] << 8)
                yon = mime == 0xFFFF
                if not tam and (tampon[g + 3] != ns_bayt or not (yon or mime in html)):
                    continue
                bas = g + (12 if yon else 16)
                s1 = tampon.index(b"\0", bas)
                s2 = tampon.index(b"\0", s1 + 1)
                baslik = (tampon[s1 + 1:s2] or tampon[bas:s1]).decode("utf-8", "replace").replace("\n", " ")
                kova, anahtar = sira_parcasi(baslik)
                kayit.append(bytes((kova,)) + anahtar.encode("utf-8") + b"\0" + duz(baslik).encode("utf-8") + b"\0"
                             + struct.pack(">I", i | (cls.YON if yon else 0)))
                if ilerleme and not sayac % 20000:
                    ilerleme(int(sayac * 80 / len(hedefler)))
        kayit.sort()
        if ilerleme:
            ilerleme(90)
        parca, konum, kova_say, grup = [b""], 1, [0] * len(HARFLER), {}
        for j, r in enumerate(kayit):
            t = r[r.index(b"\0", 1) + 1:-5]
            i = struct.unpack(">I", r[-4:])[0]
            d.idx.append(i)
            d.ofs.append(konum)
            konum += len(t) + 1
            parca.append(t)
            if i & cls.YON:
                continue
            d.mad.append(j)
            kova_say[r[0]] += 1
            # Bölüm: "Yemek:Mercimek çorbası" ya da "3B Baskı/Bakım" gibi ortak ön ekler.
            p = min([x for x in (t.find(b":", 2), t.find(b"/", 2)) if x > 0] or [0])
            if p and p + 1 < len(t) and t[p + 1] != 32 and t[p - 1] != 32:
                a = t[:p + 1]
                s = grup.get(a)
                if s is None:
                    grup[a] = [1, j]
                else:
                    s[0] += 1
        del kayit
        d.ofs.append(konum)
        d.duz = b"\n".join(parca) + b"\n"
        bas = 0
        for k, adet in enumerate(kova_say):
            d.kova[HARFLER[k]] = (bas, bas + adet)
            bas += adet
        for a, (adet, j) in sorted(grup.items(), key=lambda x: -x[1][0])[:150]:
            if adet < 5:
                break
            anahtar = a.decode("utf-8", "replace")
            d.bolum.append({"ad": z.giris(d.idx[j])["baslik"][:len(anahtar) - 1], "anahtar": anahtar, "adet": adet})
        return d

    # ---- diske yazma / diskten okuma ----
    def kaydet(self, yol, imza):
        bas = json.dumps({"surum": self.SURUM, "imza": imza, "bayt": sys.byteorder, "n": len(self.idx),
                          "nm": len(self.mad), "kova": self.kova, "bolum": self.bolum}).encode("utf-8")
        with open(yol + ".yarim", "wb") as f:
            f.write(b"IMD1" + struct.pack("<I", len(bas)) + bas)
            for parca in (self.idx.tobytes(), self.ofs.tobytes(), self.mad.tobytes(), self.duz):
                f.write(parca)
        os.replace(yol + ".yarim", yol)

    @classmethod
    def yukle(cls, yol, imza):
        try:
            with open(yol, "rb") as f:
                if f.read(4) != b"IMD1":
                    return None
                b = json.loads(f.read(struct.unpack("<I", f.read(4))[0]).decode("utf-8"))
                if b.get("surum") != cls.SURUM or b.get("imza") != imza or b.get("bayt") != sys.byteorder:
                    return None
                d = cls()
                d.idx.frombytes(f.read(4 * b["n"]))
                d.ofs.frombytes(f.read(4 * (b["n"] + 1)))
                d.mad.frombytes(f.read(4 * b["nm"]))
                d.duz = f.read()
                d.kova = {k: tuple(v) for k, v in b["kova"].items()}
                d.bolum = b["bolum"]
                if len(d.idx) != b["n"] or len(d.ofs) != b["n"] + 1 or len(d.duz) != d.ofs[-1]:
                    return None
                return d
        except Exception:
            return None

    # ---- sorgular ----
    def _madde(self, z, j, gorulen=None):
        """Sıralı konumdaki başlığı {baslik, yol} olarak döner; yönlendirmeyse asıl maddeye çözer."""
        g = z.giris(self.idx[j])
        h = z.coz(g["i"]) if "yonlendirme" in g else g
        if "yonlendirme" in h:  # çözülemeyen yönlendirme
            return None
        if gorulen is not None:
            if h["i"] in gorulen:
                return None
            gorulen.add(h["i"])
        m = {"baslik": g["baslik"], "yol": h["ns"] + "/" + h["url"]}
        if h is not g and h["baslik"] != g["baslik"]:
            m["hedef"] = h["baslik"]
        return m

    def liste(self, z, harf, bas=0, adet=200):
        a, b = self.kova.get(harf, (0, 0))
        son = min(a + bas + adet, b)
        out = [self._madde(z, j) for j in self.mad[a + bas:son]]
        return [m for m in out if m], (son - a if son < b else None), b - a

    def _tara(self, igne, p=0):
        """Düz metinde iğneyi arar; her eşleşen başlığın (sıralı konum, sonraki arama konumu) çiftini verir."""
        ek = 1 if igne[:1] == b"\n" else 0
        while True:
            p = self.duz.find(igne, p)
            if p < 0:
                return
            j = bisect.bisect_right(self.ofs, p + ek) - 1
            p = self.ofs[j + 1] - 1
            yield j, p

    def ara(self, z, sorgu, adet=25):
        """Başlıkta arama: önce başında geçenler, sonra bir kelimenin başında, sonra herhangi bir yerinde."""
        s = " ".join(duz(sorgu).split())
        if not s:
            return []
        kel, out, gorulen, bakilan = s.encode("utf-8"), [], set(), set()
        # s: eşleşme sınıfı — 0 adı tam tutan ("savas" yazınca "Savaş"), 1 başında, 2 bir kelimenin başında, 3 içinde.
        for sinif, igne in enumerate((b"\n" + kel + b"\n", b"\n" + kel, b" " + kel, kel)):
            for j, _ in self._tara(igne):
                if j in bakilan:
                    continue
                if len(bakilan) > 3000:  # aynı maddeye giden binlerce yönlendirmede takılma
                    return out
                bakilan.add(j)
                m = self._madde(z, j, gorulen)
                if m:
                    m["s"] = sinif
                    out.append(m)
                    if len(out) >= adet:
                        return out
        if not out and b" " in kel:  # kelimeler başka sırada geçiyor olabilir
            kelimeler = sorted(kel.split(), key=len, reverse=True)
            for sayac, (j, _) in enumerate(self._tara(kelimeler[0])):
                if sayac > 50000:
                    break
                t = self.duz[self.ofs[j]:self.ofs[j + 1] - 1]
                if all(k in t for k in kelimeler[1:]):
                    m = self._madde(z, j, gorulen)
                    if m:
                        out.append(m)
                        if len(out) >= adet:
                            break
        return out

    def onekle(self, z, anahtar, bas=0, adet=200):
        """Başlığı verilen ön ekle başlayan maddeler (bölüm listesi). bas: önceki çağrının döndürdüğü imleç."""
        out, son = [], None
        for j, p in self._tara(b"\n" + duz(anahtar).encode("utf-8"), bas):
            if self.idx[j] & self.YON:
                continue
            if len(out) >= adet:
                return out, son
            m = self._madde(z, j)
            if m:
                out.append(m)
            son = p
        return out, None

    def rastgele(self, z):
        return self._madde(z, self.mad[random.randrange(len(self.mad))]) if len(self.mad) else None


KITAPLAR = {}
KITAP_KILIT = threading.Lock()
DIZIN = {}        # kitap id -> Dizin (hazır olanlar)
DIZIN_DURUM = {}  # kitap id -> {"durum": "sirada" | "hazirlaniyor" | "hazir" | "yok", "yuzde": 0-100}
DIZIN_SIRA = queue.Queue()
DIZIN_SINIR = 2500000  # bundan çok başlığı olan kitap belleğe alınmaz, sade kipte çalışır


def kitap_id(dosya):
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", os.path.splitext(dosya)[0])


def dizin_isi():
    """Tek iş parçacığı: kitapların başlık dizinlerini sırayla hazırlar."""
    while True:
        kid, z = DIZIN_SIRA.get()
        st = DIZIN_DURUM.get(kid)
        if st is None or KITAPLAR.get(kid) is not z:
            continue
        try:
            try:  # ayarlar.json içinde "dizin_sinir" ile değiştirilebilir (az bellekli cihazlar için)
                sinir = int(ayar_oku().get("dizin_sinir", DIZIN_SINIR))
            except (TypeError, ValueError):
                sinir = DIZIN_SINIR
            if z.baslik_dizini()[1] > sinir:
                st.update(durum="yok", neden="buyuk")
                continue
            ddir = os.path.join(os.path.dirname(os.path.dirname(z.yol)), "dizin")
            dyol = os.path.join(ddir, kid + ".imd")
            d = Dizin.yukle(dyol, z.imza)
            if d is None:
                st.update(durum="hazirlaniyor", yuzde=0)
                t0 = time.time()
                d = Dizin.kur(z, lambda y: st.update(yuzde=y))
                print("  dizin hazır: %s (%d başlık, %.1f sn)" % (kid, len(d.idx), time.time() - t0))
                try:
                    os.makedirs(ddir, exist_ok=True)
                    d.kaydet(dyol, z.imza)
                    if not os.path.exists(z.yol):  # dizin kurulurken kitap silinmiş: dosyası geride kalmasın
                        os.remove(dyol)
                except Exception as e:  # salt okunur disk: dizin her açılışta yeniden kurulur
                    print("  ! dizin diske yazılamadı:", e)
            if KITAPLAR.get(kid) is z:
                DIZIN[kid] = d
                st.update(durum="hazir", yuzde=100)
        except Exception as e:
            st.update(durum="yok", neden=str(e))
            print("  ! dizin kurulamadı:", kid, e)


TARAMA_DURDU = [False]  # veri klasörü taşınırken kitaplar kapalı kalır; tarama onları eski yerinden yeniden açmasın


def kitaplari_tara():
    if TARAMA_DURDU[0]:
        return KITAPLAR
    zdir = os.path.join(veri_dir(), "zim")
    bulunan = {}
    for d in sorted(os.listdir(zdir)):
        if d.lower().endswith(".zim"):
            bulunan[kitap_id(d)] = os.path.join(zdir, d)
    with KITAP_KILIT:
        for k in list(KITAPLAR):
            if k not in bulunan or KITAPLAR[k].yol != bulunan[k]:
                eski = KITAPLAR.pop(k)
                DIZIN.pop(k, None)
                DIZIN_DURUM.pop(k, None)
                TM_DURUM.pop(k, None)
                try:
                    eski.kapat()
                    if not os.path.exists(eski.yol):  # kitap silinmiş: dizin dosyaları da gitsin
                        tm_sil(tm_yolu(eski, k))
                        tm_sil(tm_yolu(eski, k) + ".yarim")
                        os.remove(os.path.join(os.path.dirname(os.path.dirname(eski.yol)), "dizin", k + ".imd"))
                except Exception:
                    pass
        for k, yol in bulunan.items():
            if k not in KITAPLAR:
                try:
                    KITAPLAR[k] = Zim(yol)
                    DIZIN_DURUM[k] = {"durum": "sirada", "yuzde": 0}
                    TM_DURUM[k] = {"durum": "sirada", "yuzde": 0}
                    DIZIN_SIRA.put((k, KITAPLAR[k]))
                    TM_UYAN.set()
                except Exception as e:
                    print("  ! açılamadı:", yol, e)
    return KITAPLAR


DILLER = {"tur": "Türkçe", "tr": "Türkçe", "eng": "İngilizce", "en": "İngilizce", "mul": "Çok dilli"}


def kitap_listesi():
    out = []
    for k, z in sorted(kitaplari_tara().items()):
        m = z.meta()
        d = DIZIN.get(k)
        out.append({"id": k, "baslik": m.get("Title") or k, "aciklama": m.get("Description", ""),
                    "dil": m.get("Language", ""), "tarih": m.get("Date", ""),
                    "boyut_mb": round(os.path.getsize(z.yol) / MB), "ana": z.ana_sayfa_url(),
                    "madde": len(d.mad) if d else z.madde_tahmini(), "madde_kesin": d is not None,
                    "tam_metin": (TM_DURUM.get(k) or {}).get("durum", "yok"),
                    "dosya": os.path.basename(z.yol), "imza": z.imza})  # başka bir İmece bu kitabı alırken kullanır
    return out


def kitap_ozet(kid):
    """Kitap giriş ekranının verisi."""
    z = kitaplari_tara().get(kid)
    if not z:
        return None
    m = z.meta()
    st = dict(DIZIN_DURUM.get(kid) or {"durum": "yok"})
    if st["durum"] in ("sirada", "hazirlaniyor"):  # küçük kitaplarda dizin bir saniyeden kısa sürer: bekle
        for _ in range(15):
            if kid in DIZIN:
                break
            time.sleep(0.1)
        st = dict(DIZIN_DURUM.get(kid) or {"durum": "yok"})
    d = DIZIN.get(kid)
    if d:
        harfler = [{"harf": h, "adet": d.kova[h][1] - d.kova[h][0]} for h in HARFLER]
        madde, bolumler = len(d.mad), d.bolum
    else:
        harfler = [{"harf": h, "adet": sum(b - a for a, b in z.sade_aralik(h))} for h in HARFLER]
        madde, bolumler = z.madde_tahmini(), []
    dil = m.get("Language", "")
    return {"id": kid, "baslik": m.get("Title") or kid, "aciklama": m.get("Description", ""),
            "uzun_aciklama": m.get("LongDescription", ""), "dil": dil,
            "dil_adi": ", ".join(DILLER.get(x, x) for x in dil.split(",")) if dil else "",
            "tarih": m.get("Date", ""), "boyut_mb": round(os.path.getsize(z.yol) / MB),
            "hazirlayan": m.get("Creator", ""), "yayinci": m.get("Publisher", ""), "kaynak": m.get("Source", ""),
            "lisans": m.get("License", ""), "cesit": m.get("Flavour", ""), "dosya": os.path.basename(z.yol),
            "madde": madde, "madde_kesin": d is not None, "baslik_adet": len(d.idx) if d else z.baslik_dizini()[1],
            "ana": z.ana_sayfa_url(), "simge": z.simge_url(), "dizin": st, "tam_metin": dict(TM_DURUM.get(kid) or {"durum": "yok"}),
            "harfler": harfler, "bolumler": bolumler}


def kitapta_ara(kid, z, sorgu, adet):
    d = DIZIN.get(kid)
    return d.ara(z, sorgu, adet) if d else z.baslik_ara(sorgu, adet)


# =====================================================================
#  TAM METİN DİZİNİ
#  Maddelerin yazısının içinde arama. Her kitap için arka planda bir kere kurulur ve
#  veri/dizin/<kitap>.imt dosyasına yazılır. Depo olarak SQLite'ın tam metin eklentisi (FTS5)
#  kullanılır; Python'un standart kitaplığının parçasıdır, ayrıca bir şey kurulmaz.
#  Kurulum yarıda kalırsa (İmece kapanırsa) bir sonraki açılışta kaldığı yerden sürer.
# =====================================================================
try:
    import sqlite3
    _c = sqlite3.connect(":memory:")
    _c.execute("CREATE VIRTUAL TABLE t USING fts5(a)")
    _c.close()
    TM_VAR = True
except Exception:  # bu Python'da SQLite ya da FTS5 yok: tam metin arama kapalı kalır, gerisi çalışır
    sqlite3 = None
    TM_VAR = False

TM_SURUM = 1       # dizin düzeni ya da sadeleştirme değişince artır: eski dosyalar kendiliğinden yeniden kurulur
TM_AZAMI = 2000000  # tek maddeden dizine alınan en çok harf
TM_DURUM = {}      # kitap id -> {"durum": "sirada" | "hazirlaniyor" | "hazir" | "kapali" | "yok", "yuzde", "boyut_mb", "neden"}
TM_DUR = threading.Event()   # İmece kapanırken: süren kurulum en yakın kayıt noktasında durur
TM_UYAN = threading.Event()  # işçiyi beklemeden uyandırır (yeni kitap, ayar değişti)
TM_MESGUL = threading.Event()  # işçi şu an bir dizin dosyasına yazıyor
TM_SUREN = [None]              # işçinin şu an dizinini kurduğu kitap
SILINEN = set()                # silinmekte olan kitaplar (dizin işçileri arkalarında dosya bırakmasın)

# Sadeleştirme: küçük harf + noktasız, şapkasız (ısı = isi = ISI, şiir = siir, é = e). Her harf tek harfe
# çevrilir; metnin uzunluğu değişmez, böylece özetteki vurgu konumları asıl metinle birebir tutar.
_TM_TABLO = {}
for _k in range(0xC0, 0x250):
    _t = unicodedata.normalize("NFD", chr(_k))[0]
    if _t != chr(_k) and _t.isascii() and _t.isalpha():
        _TM_TABLO[_k] = _t.lower()
_TM_TABLO.update({ord(_a): _b for _a, _b in zip("IİıçÇğĞöÖşŞüÜ", "iiiccggoossuu")})
_TM_ETIKET = re.compile(rb"<[^>]*>")
_TM_GIZLI = re.compile(rb"<(script|style|noscript|template)\b.*?</\1\s*>", re.S | re.I)
_TM_KELIME = r"[^\W_]"  # harf ya da rakam


def tm_sade(s):
    return s.translate(_TM_TABLO).lower()


def html_metin(veri):
    """HTML sayfanın okunan yazısı: etiketler, betikler ve biçim tanımları atılır."""
    p = veri.find(b"<body")
    if p > 0:
        veri = veri[p:]
    if b"<script" in veri or b"<style" in veri or b"<noscript" in veri or b"<template" in veri:
        veri = _TM_GIZLI.sub(b" ", veri)
    return _html.unescape(_TM_ETIKET.sub(b" ", veri).decode("utf-8", "replace"))


def tm_yolu(z, kid):
    return os.path.join(os.path.dirname(os.path.dirname(z.yol)), "dizin", kid + ".imt")


def tm_acik():
    return TM_VAR and bool(ayar_oku().get("tam_metin", True))


def tm_sil(yol):
    """Dizin dosyasını ve SQLite'ın yan dosyalarını siler. Silinen bayt sayısını döner."""
    n = 0
    for ek in ("", "-wal", "-shm", "-journal"):
        try:
            b = os.path.getsize(yol + ek)
            os.remove(yol + ek)
            n += b
        except OSError:
            pass
    return n


def tm_bilgi(yol):
    """Dizin dosyasının künyesi (sürüm, paket imzası, kaç madde işlendi); okunamıyorsa None."""
    if not os.path.exists(yol):
        return None
    try:
        c = sqlite3.connect(yol)
        try:
            return dict(c.execute("SELECT ad, deger FROM bilgi").fetchall())
        finally:
            c.close()
    except Exception:
        return None


def tm_konumlar(z, girdiler):
    """Maddelerin paketteki yerleri, okuma sırasına dizilmiş: her biri (küme << 64) | (blob << 32) | girdi no.
    Aynı kümedeki maddeler art arda gelir; küme bir kere açılır. Sıra her çalıştırmada aynıdır (kaldığı yerden
    sürdürmek buna dayanır)."""
    out = []
    with open(z.yol, "rb") as f:
        f.seek(z.url_ptr)
        ptr = array("Q")
        ptr.frombytes(f.read(8 * z.n))
        if sys.byteorder == "big":
            ptr.byteswap()
        tampon, tbas, pen = b"", -1, 1 << 20
        for i in sorted(girdiler, key=ptr.__getitem__):
            g = ptr[i] - tbas
            if tbas < 0 or g < 0 or len(tampon) - g < 16:
                f.seek(ptr[i])
                tampon, tbas, g = f.read(pen), ptr[i], 0
            if tampon[g] | (tampon[g + 1] << 8) == 0xFFFF:  # yönlendirme
                continue
            kume, blob = struct.unpack_from("<II", tampon, g + 8)
            out.append((kume << 64) | (blob << 32) | i)
    out.sort()
    return out


def tam_metin_kur(kid, z, d, st):
    """Kitabın tam metin dizinini kurar ya da kaldığı yerden sürdürür. True: bitti; False: durduruldu."""
    yol = tm_yolu(z, kid)
    yarim = yol + ".yarim"
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    b = tm_bilgi(yarim)
    if not b or b.get("imza") != z.imza or b.get("surum") != TM_SURUM:
        tm_sil(yarim)
        b = None
    # Kaldığı yer hemen görünsün (yeniden açılışta yüzde sıfırdan başlamış gibi durmasın).
    st.update(durum="hazirlaniyor", yuzde=min(99, int(b["konum"]) * 100 // max(1, len(d.mad))) if b else 0)
    c = sqlite3.connect(yarim)
    try:
        # WAL: her kayıt noktası tek parça yazılır; İmece o sırada kapansa da dosya bozulmaz.
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        if b is None:
            c.execute("CREATE VIRTUAL TABLE m USING fts5(baslik, govde, content='', tokenize=\"unicode61 remove_diacritics 2\")")
            c.execute("CREATE TABLE bilgi(ad TEXT PRIMARY KEY, deger)")
            c.executemany("INSERT INTO bilgi VALUES(?,?)", [("surum", TM_SURUM), ("imza", z.imza), ("konum", 0), ("madde", 0)])
            c.commit()
            konum = madde = 0
        else:
            konum, madde = int(b["konum"]), int(b["madde"])
        z2 = Zim(z.yol)  # kendi dosya tutamacı ve önbelleği: okuyan isteklerle çakışmaz
        try:
            sira = tm_konumlar(z2, [d.idx[j] for j in d.mad])
            toplam = len(sira) or 1
            st.update(yuzde=min(99, konum * 100 // toplam))
            html_mime = {i for i, m in enumerate(z2.mimeler) if "html" in m}
            parti = []

            def yaz(yeni_konum):  # maddeler ve "nereye kadar geldik" bilgisi aynı kayıtta: ya ikisi de yazılır ya hiçbiri
                nonlocal madde
                c.executemany("INSERT INTO m(rowid, baslik, govde) VALUES(?,?,?)", parti)
                madde += len(parti)
                parti.clear()
                c.execute("UPDATE bilgi SET deger=? WHERE ad='konum'", (yeni_konum,))
                c.execute("UPDATE bilgi SET deger=? WHERE ad='madde'", (madde,))
                c.commit()
                st.update(yuzde=min(99, yeni_konum * 100 // toplam), madde=madde)

            for n in range(konum, len(sira)):
                a = sira[n]
                g = z2.giris(a & 0xFFFFFFFF)
                if g.get("mime") in html_mime:
                    veri, of = z2.kume(a >> 64)
                    blob = (a >> 32) & 0xFFFFFFFF
                    parti.append((g["i"], tm_sade(g["baslik"]), tm_sade(html_metin(veri[of[blob]:of[blob + 1]]))[:TM_AZAMI]))
                if len(parti) >= 300:
                    yaz(n + 1)
                    if TM_DUR.is_set() or KITAPLAR.get(kid) is not z or not tm_acik():
                        return False
            yaz(len(sira))
        finally:
            z2.kapat()
        st.update(yuzde=99)
        c.execute("INSERT INTO m(m) VALUES('optimize')")  # parçaları birleştir: dosya küçülür, arama hızlanır
        c.execute("INSERT OR REPLACE INTO bilgi VALUES('tamam', 1)")
        c.commit()
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.execute("PRAGMA journal_mode=DELETE")  # tek dosya kalsın (flash'a kopya, salt okunur disk)
    finally:
        c.close()
    tm_sil(yol)
    os.replace(yarim, yol)
    return True


def tam_metin_isi():
    """Tek iş parçacığı: önce hazır dizinleri tanır, sonra eksik olanları küçük kitaptan büyüğe sırayla kurar."""
    while True:
        TM_UYAN.wait(3)
        TM_UYAN.clear()
        if TM_DUR.is_set():
            continue
        try:
            kitaplar = sorted(list(KITAPLAR.items()), key=lambda x: os.path.getsize(x[1].yol))
        except OSError:
            continue
        acik = tm_acik()
        aday = None
        for kid, z in kitaplar:
            st = TM_DURUM.get(kid)
            if st is None or st["durum"] not in ("sirada", "kapali"):
                continue
            if not TM_VAR:
                st.update(durum="yok", neden="fts5")
                continue
            yol = tm_yolu(z, kid)
            b = tm_bilgi(yol)
            if b and b.get("imza") == z.imza and b.get("surum") == TM_SURUM and b.get("tamam"):
                st.update(durum="hazir", yuzde=100, madde=int(b.get("madde") or 0), boyut_mb=round(os.path.getsize(yol) / MB, 1))
                continue
            if not acik:
                st.update(durum="kapali")
                continue
            st.update(durum="sirada")
            if kid in DIZIN:
                aday = aday or (kid, z, st)
            elif (DIZIN_DURUM.get(kid) or {}).get("durum") == "yok":
                st.update(durum="yok", neden="buyuk")
        if not aday:
            continue
        kid, z, st = aday
        yol = tm_yolu(z, kid)
        try:
            os.makedirs(os.path.dirname(yol), exist_ok=True)
            # Dizin, kitabın yarısı kadar yer tutabilir. Disk dolmasın diye baştan bakılır.
            yarim_boy = os.path.getsize(yol + ".yarim") if os.path.exists(yol + ".yarim") else 0
            gereken = max(50 * MB, int(os.path.getsize(z.yol) * 0.7)) - yarim_boy + 200 * MB
            if shutil.disk_usage(os.path.dirname(yol)).free < gereken:
                st.update(durum="yok", neden="yer", gereken_mb=round(gereken / MB))
                continue
            TM_MESGUL.set()
            TM_SUREN[0] = kid
            t0 = time.time()
            bitti = tam_metin_kur(kid, z, DIZIN[kid], st)
            if bitti and KITAPLAR.get(kid) is z:
                st.update(durum="hazir", yuzde=100, boyut_mb=round(os.path.getsize(yol) / MB, 1))
                print("  tam metin dizini hazır: %s (%d madde, %.0f sn, %.0f MB)" % (kid, st.get("madde", 0), time.time() - t0, st["boyut_mb"]), flush=True)
            else:
                st.update(durum="sirada")
        except Exception as e:
            st.update(durum="yok", neden=str(e))
            print("  ! tam metin dizini kurulamadı:", kid, e, flush=True)
            tm_sil(yol + ".yarim")  # bozulmuş olabilir: bir sonraki açılışta baştan kurulur
        finally:
            # Kitap bu arada silindiyse dizini (yarım ya da bitmiş) geride kalmasın. Silen taraf dosyaları
            # biz kapatmadan silemez; o yüzden temizlik burada, dosyalar kapandıktan sonra yapılır.
            if kid in SILINEN or not os.path.exists(z.yol):
                tm_sil(yol)
                tm_sil(yol + ".yarim")
            TM_SUREN[0] = None
            TM_MESGUL.clear()
        TM_UYAN.set()


_TM_UNLU = frozenset("aeiou")  # sadeleştirilmiş ünlüler (ı, ö, ü de bunlara iner)
_TM_YUMUSAK = {"p": "b", "t": "d", "k": "g"}  # kitap → kitabı, kağıt → kağıdı, çocuk → çocuğu (ç → c sadeleştirmede zaten aynıdır)


def tm_yumusak(k):
    """Türkçe ünsüz yumuşaması. Sonu p, t ya da k ile biten çok heceli kelime, ünlüyle başlayan ek alınca
    b, d, ğ ile yazılır ("kitap" → "kitabı", "çocuk" → "çocuğu"); ön ek araması bunları tek başına bulamaz.
    Sadeleştirilmiş kelimenin yumuşamış gövdesini döner ("kitab"); kural uygulanmıyorsa None.
    Tek heceliler çoğunlukla yumuşamadığı için ("at" → "atı", "kart" → "kartı") dışarıda bırakılır;
    yalnızca "-nk" ile bitenler ("renk" → "rengi") alınır. Gövdesi değişmeyen kelimelerde ("millet" → "milleti")
    eklenen biçimler dizinde hiçbir şeyle eşleşmez; zararsızdır."""
    if len(k) < 4 or not k.isascii() or k[-1] not in _TM_YUMUSAK:
        return None
    if sum(1 for c in k if c in _TM_UNLU) < 2 and not k.endswith("nk"):
        return None
    return k[:-1] + _TM_YUMUSAK[k[-1]]


def tm_sorgu(sorgu):
    """Yazılanı dizin sorgusuna çevirir: (hepsi geçsin, herhangi biri geçsin, [(kelime, ön ek mi)]).
    Üç harf ve üstü kelimeler ön ek sayılır: Türkçe ekler ("peroksit" → peroksitin, peroksitler) böyle yakalanır.
    Tırnak içine yazılan söz öbeği, kelimeleri o sırayla yan yana arar."""
    ogeler = []  # (dizin ifadesi, en kısa kelimesinin boyu, [(vurgulanacak kelime, ön ek mi)])
    for m in re.finditer(r'"([^"]+)"|(%s+)' % _TM_KELIME, tm_sade(sorgu)):
        if m.group(1) is not None:
            k = re.findall(_TM_KELIME + "+", m.group(1))
            if k:
                ogeler.append(('"%s"' % " ".join(k), max(len(x) for x in k), [(x, False) for x in k]))
        else:
            k = m.group(2)
            y = tm_yumusak(k)
            if y:  # "kitap" → kitap…, kitaba…, kitabe…, kitabı…, kitabo…, kitabu… (yumuşayan ünsüzden sonra ünlü gelir)
                ogeler.append(("(%s)" % " OR ".join(['"%s"*' % k] + ['"%s%s"*' % (y, u) for u in "aeiou"]), len(k), [(k, True)] + [(y + u, True) for u in "aeiou"]))
            else:
                ogeler.append(('"%s"%s' % (k, "*" if len(k) >= 3 else ""), len(k), [(k, len(k) >= 3)]))
    if len(ogeler) > 1 and any(o[1] > 1 for o in ogeler):  # tek harfli kelimeler ("a", "o") aramayı sadece yavaşlatır
        ogeler = [o for o in ogeler if o[1] > 1]
    ogeler = ogeler[:8]
    parcalar = [o[0] for o in ogeler]
    return " AND ".join(parcalar), " OR ".join(parcalar), [k for o in ogeler for k in o[2]][:48]


def tm_ozet(z, g, kelimeler, genislik=200):
    """Maddenin yazısından, aranan kelimenin geçtiği yerin çevresini keser. (özet, [[baş, son], …] vurgu konumları)"""
    try:
        metin = " ".join(html_metin(z.icerik(g)).split())
    except Exception:
        return "", []
    sade = tm_sade(metin)
    if len(sade) != len(metin) or not kelimeler:
        return metin[:genislik], []
    desen = re.compile("(?<!%s)(?:%s)" % (_TM_KELIME, "|".join(
        "(%s%s)" % (re.escape(k), _TM_KELIME + "*" if onek else "(?!%s)" % _TM_KELIME) for k, onek in sorted(kelimeler, key=lambda x: -len(x[0])))))
    # Aranan kelimelerin en çoğunun bir arada geçtiği yer seçilir (ilk 300 eşleşme içinde).
    m, en_iyi, gecen = None, 0, []
    for x in desen.finditer(sade):
        gecen.append(x)
        if len(gecen) >= 300:
            break
    for n, x in enumerate(gecen):
        cesit = {y.lastindex for y in gecen[n:n + 12] if y.start() - x.start() < 130}
        if len(cesit) > en_iyi:
            m, en_iyi = x, len(cesit)
            if en_iyi == len(kelimeler):
                break
    bas = 0
    if m and m.start() > 80:
        bas = m.start() - 70
        p = sade.find(" ", bas, m.start())
        bas = p + 1 if p >= 0 else bas
    son = min(len(metin), bas + genislik)
    if son < len(metin):
        p = sade.rfind(" ", bas + 60, son)
        son = p if p > 0 else son
    on = "… " if bas else ""
    vurgu = [[x.start() - bas + len(on), x.end() - bas + len(on)] for x in desen.finditer(sade, bas, son)][:12]
    return on + metin[bas:son] + (" …" if son < len(metin) else ""), vurgu


def tm_ara(kid, z, sorgu, adet=20, bas=0):
    """Kitabın maddelerinin yazısında arar. (sonuçlar, devamı var mı, bütün kelimeler geçiyor mu)"""
    hepsi, biri, kelimeler = tm_sorgu(sorgu)
    if not hepsi or (TM_DURUM.get(kid) or {}).get("durum") != "hazir":
        return [], False, True
    c = sqlite3.connect(tm_yolu(z, kid))
    try:
        c.execute("PRAGMA query_only=1")

        def sor(ifade):
            # Çok yaygın bir kelimede ("ve") yüz binlerce maddeyi puanlamak uzun sürer: süre dolarsa sırasız ilk sonuçlar verilir.
            son = time.time() + 3
            c.set_progress_handler(lambda: 1 if time.time() > son else 0, 20000)
            try:
                return c.execute("SELECT rowid, bm25(m, 8.0, 1.0) FROM m WHERE m MATCH ? ORDER BY bm25(m, 8.0, 1.0) LIMIT ? OFFSET ?",
                                 (ifade, adet + 1, bas)).fetchall()
            except sqlite3.OperationalError:
                son = time.time() + 3
                try:
                    return c.execute("SELECT rowid, 0 FROM m WHERE m MATCH ? LIMIT ? OFFSET ?", (ifade, adet + 1, bas)).fetchall()
                except sqlite3.OperationalError:
                    return []

        satirlar, tumu = sor(hepsi), True
        if not satirlar and not bas and biri != hepsi:
            satirlar, tumu = sor(biri), False
    finally:
        c.close()
    out = []
    for i, puan in satirlar[:adet]:
        g = z.giris(i)
        if "yonlendirme" in g:
            continue
        ozet, vurgu = tm_ozet(z, g, kelimeler)
        out.append({"baslik": g["baslik"], "yol": g["ns"] + "/" + g["url"], "ozet": ozet, "vurgu": vurgu, "puan": round(puan, 3)})
    return out, len(satirlar) > adet, tumu


def tm_ozet_durum():
    """Bütün kitaplar için tam metin dizininin durumu (Ayarlar ve arama ekranı için)."""
    st = {k: dict(v) for k, v in list(TM_DURUM.items())}
    hazir = [v for v in st.values() if v["durum"] == "hazir"]
    suren = next(({"kitap": k, "yuzde": v.get("yuzde", 0)} for k, v in st.items() if v["durum"] == "hazirlaniyor"), None)
    return {"var": TM_VAR, "acik": tm_acik(), "toplam": len(st), "hazir": len(hazir),
            "sirada": len([1 for v in st.values() if v["durum"] in ("sirada", "hazirlaniyor")]),
            "boyut_mb": round(sum(v.get("boyut_mb", 0) for v in hazir), 1), "suren": suren}


# =====================================================================
#  İNDİRME YÖNETİCİSİ
# =====================================================================
KATALOG = "https://library.kiwix.org/catalog/v2/entries"
NS = {"a": "http://www.w3.org/2005/Atom"}
IS = {"aktif": False, "mevcut": "", "yuzde": None, "mb": 0, "hiz": 0, "kuyruk": [], "log": [], "dur": False,
      "bekleyen": []}  # bekleyen: duraklatılan ya da yarıda kalan indirmeler (Devam et ile sürer)
IS_KILIT = threading.Lock()


def sira_dosyasi():
    return os.path.join(veri_dir(), "sira.json")


def sira_kaydet(ogeler):
    """Yarıda kalan indirmeleri diske yazar: İmece kapansa da 'Devam et' ile sürdürülebilir."""
    try:
        if ogeler:
            with open(sira_dosyasi(), "w", encoding="utf-8") as f:
                json.dump(ogeler, f, ensure_ascii=False)
        elif os.path.exists(sira_dosyasi()):
            os.remove(sira_dosyasi())
    except Exception:
        pass


def sira_yukle():
    try:
        with open(sira_dosyasi(), encoding="utf-8") as f:
            IS["bekleyen"] = [o for o in json.load(f) if isinstance(o, dict) and o.get("id") and o.get("tur")]
    except Exception:
        IS["bekleyen"] = []


def log(m):
    with IS_KILIT:
        IS["log"] = (IS["log"] + [time.strftime("%H:%M ") + m])[-30:]
    print(m)


def paketler():
    with open(os.path.join(UYG, "katalog.json"), encoding="utf-8") as f:
        return json.load(f)


def durum_oku():
    p = os.path.join(veri_dir(), "durum.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def durum_yaz(d):
    with open(os.path.join(veri_dir(), "durum.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def opds_sec(xml, ad, flavour):
    kok = ET.fromstring(xml)
    aday = []
    for e in kok.findall("a:entry", NS):
        if (e.findtext("a:name", "", NS) or "").strip() != ad:
            continue
        fl = (e.findtext("a:flavour", "", NS) or "").strip()
        tarih = e.findtext("a:updated", "", NS) or ""
        for l in e.findall("a:link", NS):
            if l.get("type") == "application/x-zim":
                href = l.get("href", "")
                if href.endswith(".meta4"):
                    href = href[:-6]
                aday.append((fl, tarih, href, int(l.get("length") or 0) or None))
    if not aday:
        return None
    uygun = [a for a in aday if not flavour or a[0] == flavour]
    if uygun:
        uygun.sort(key=lambda a: a[1], reverse=True)
    else:
        sira = {"nopic": 0, "mini": 1}
        uygun = sorted(aday, key=lambda a: (sira.get(a[0], 2), [-ord(c) for c in a[1]]))
    _, _, href, boyut = uygun[0]
    return href, boyut, os.path.basename(urllib.parse.urlparse(href).path)


def katalog_coz(ad, flavour, dil):
    sorgular = [{"name": ad, "count": "50"}, {"q": ad, "count": "100"}]
    if dil:
        sorgular.append({"lang": dil, "count": "500"})
    for s in sorgular:
        try:
            with urllib.request.urlopen(urllib.request.Request(KATALOG + "?" + urllib.parse.urlencode(s), headers=UA), timeout=60) as r:
                c = opds_sec(r.read(), ad, flavour)
            if c:
                return c
        except Exception as e:
            log("katalog hatası: %s" % e)
    return None


HATA_BEKLE = 10  # indirme hatasından sonra yeniden denemeden önce beklenen saniye


class Durduruldu(Exception):
    pass


class Bozuk(Exception):
    """İnen dosyanın sağlaması tutmadı."""


def zim_saglama(yol, ilerleme=None, dur=None):
    """Kitap dosyasının kendi içindeki sağlamayı denetler: son 16 bayt, öncesinin MD5 özetidir.
    (sağlam mı, sağlam değilse neden) döner. dur() doğru dönerse Durduruldu fırlatır."""
    boy = os.path.getsize(yol)
    with open(yol, "rb") as f:
        bas = f.read(80)
        if len(bas) < 80 or struct.unpack_from("<I", bas, 0)[0] != Zim.BUYU:
            return False, "kitap dosyası değil"
        if struct.unpack_from("<Q", bas, 72)[0] != boy - 16:
            return False, "dosya eksik (boyu, içinde yazan boyla tutmuyor)"
        h, kalan = hashlib.md5(), boy - 16
        f.seek(0)
        while kalan > 0:
            if dur and dur():
                raise Durduruldu()
            p = f.read(min(4 * MB, kalan))
            if not p:
                return False, "dosya okunamadı"
            h.update(p)
            kalan -= len(p)
            if ilerleme:
                ilerleme(100 - kalan * 100 // (boy - 16))
        return (True, "") if h.digest() == f.read(16) else (False, "sağlaması tutmuyor")


def dosya_saglama_md5(yol, beklenen, dur=None):
    """Dosyanın MD5 özeti, kaynağın bildirdiği özetle aynı mı (müzik arşivi dosyaları için)."""
    h = hashlib.md5()
    with open(yol, "rb") as f:
        while True:
            if dur and dur():
                raise Durduruldu()
            p = f.read(4 * MB)
            if not p:
                break
            h.update(p)
    return h.hexdigest() == str(beklenen).lower()


def dosya_indir(url, hedef, md5=None):
    """Dosyayı indirir (yarım kalmışsa kaldığı yerden). Bittiğinde sağlaması denetlenir: kitap (.zim) dosyalarında
    dosyanın kendi içindeki sağlama, md5 verilmişse kaynağın bildirdiği özet. Tutmuyorsa dosya silinir ve Bozuk
    fırlatılır; kütüphaneye bozuk dosya girmez. Döner: sağlama denetlendi mi."""
    gecici = hedef + ".yarim"
    bas = os.path.getsize(gecici) if os.path.exists(gecici) else 0
    bh = dict(UA)
    if bas:
        bh["Range"] = "bytes=%d-" % bas
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=bh), timeout=120)
    except urllib.error.HTTPError as e:
        if not (bas and e.code == 416):
            raise
        r = None  # "istenen aralık yok": dosyanın tamamı zaten inmiş (sağlama denetimi sırasında duraklatılmış)
    if r is not None:
        with r:
            if bas and r.status != 206:
                bas = 0
            toplam = r.headers.get("Content-Length")
            toplam = int(toplam) + bas if toplam else None
            indi, t0, son = bas, time.time(), 0
            with open(gecici, "ab" if bas else "wb") as f:
                while True:
                    if IS["dur"]:
                        raise Durduruldu()
                    p = r.read(MB)
                    if not p:
                        break
                    f.write(p)
                    indi += len(p)
                    if time.time() - son > 0.5:
                        son = time.time()
                        with IS_KILIT:
                            IS["mb"] = round(indi / MB)
                            IS["yuzde"] = round(indi * 100 / toplam, 1) if toplam else None
                            IS["hiz"] = round((indi - bas) / max(son - t0, 0.1) / MB, 1)
    denetlendi = False
    if hedef.lower().endswith(".zim") or md5:
        with IS_KILIT:
            onceki = IS["mevcut"]
            IS.update({"mevcut": onceki + " — sağlaması denetleniyor", "yuzde": 0, "hiz": 0})

        def ilerle(y):
            IS["yuzde"] = y
        try:
            if hedef.lower().endswith(".zim"):
                tamam, neden = zim_saglama(gecici, ilerle, lambda: IS["dur"])
            else:
                tamam, neden = dosya_saglama_md5(gecici, md5, lambda: IS["dur"]), "özeti, kaynağın bildirdiğiyle tutmuyor"
        finally:
            with IS_KILIT:
                IS["mevcut"] = onceki
        if not tamam:
            os.remove(gecici)  # yarım dosya olarak da kalmasın: devam edilirse yine bozuk çıkardı
            raise Bozuk("inen dosya bozuk (%s); silindi" % neden)
        denetlendi = True
    os.replace(gecici, hedef)
    return denetlendi


# ---- Sanat galerileri: Wikimedia Commons'taki bir kategorinin KAMU MALI resimleri ----
# Lisansı "kamu malı" (Public domain / CC0) olarak işaretlenmemiş hiçbir dosya alınmaz. Her eserin adı, sanatçısı,
# tarihi, lisansı ve kaynak sayfası galerinin kunye.json dosyasına yazılır ve arayüzde eserin altında gösterilir.
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_GENISLIK = 960   # indirilen resmin eni. Commons küçültülmüş resimleri verir, özgün dosyaları sık sık geri çevirir (429):
                         # bu yüzden yalnızca bundan geniş resimler alınır (küçültülmüş kopyası olanlar)
COMMONS_KUCUK = 500      # eni 960'tan dar resimler için istenen boy
COMMONS_BEKLE = 4        # resimler arasında saniye: Commons art arda gelen istekleri geri çevirir (429)
COMMONS_CEZA = 20        # geri çevrilince beklenen saniye (bir kere; yine geri çevrilirse galeri sonraya bırakılır)
COMMONS_KAMU = re.compile(r"(?i)^\s*(public domain|cc0|pd\b)")


def _etiketsiz(s):
    import html as _html
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def commons_al(url):
    for deneme in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(20 * (deneme + 1))
    raise OSError("Commons şu an çok meşgul; biraz sonra yeniden dene")


def commons_liste(p):
    """Kategorideki kamu malı resimler: [(indirme adresi, dosya adı, künye)]."""
    def sor(en):
        u = COMMONS_API + "?" + urllib.parse.urlencode({
            "action": "query", "format": "json", "generator": "categorymembers", "gcmtitle": "Category:" + p["commons_kategori"],
            "gcmtype": "file", "gcmlimit": "100", "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": str(en)})
        return ((commons_al(u).get("query") or {}).get("pages") or {})
    buyuk = sor(COMMONS_GENISLIK)
    time.sleep(COMMONS_BEKLE)
    kucuk = {k: ((v.get("imageinfo") or [{}])[0].get("thumburl")) for k, v in sor(COMMONS_KUCUK).items()}  # dar resimler için
    sayfalar = sorted(buyuk.values(), key=lambda s: s.get("title", ""))
    out, adlar = [], set()
    for s in sayfalar:
        ii = (s.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata") or {}
        al = lambda k: _etiketsiz((em.get(k) or {}).get("value"))
        lisans = al("LicenseShortName")
        if ii.get("mime") not in ("image/jpeg", "image/png") or not COMMONS_KAMU.match(lisans):
            continue
        en = ii.get("width") or 0
        adres = ii.get("thumburl") if en > COMMONS_GENISLIK else (kucuk.get(str(s.get("pageid"))) if en > COMMONS_KUCUK else None)
        if not adres or (ii.get("height") or 0) < 400:
            continue  # çok küçük resim: küçültülmüş kopyası yok, özgün dosya istenirdi (Commons geri çevirir)
        baslik = s.get("title", "").split(":", 1)[-1]
        ad = re.sub(r"[^A-Za-z0-9._-]", "_", baslik)[-90:]
        if not ad.lower().endswith((".jpg", ".jpeg", ".png")):
            ad += ".jpg"
        if ad in adlar:
            continue
        adlar.add(ad)
        out.append((adres, ad, {
            "dosya": ad, "ad": al("ObjectName") or os.path.splitext(baslik)[0], "sanatci": al("Artist")[:120], "tarih": al("DateTimeOriginal")[:60],
            "lisans": lisans, "kaynak": ii.get("descriptionurl") or ""}))
        if len(out) >= int(p.get("en_cok", 40)):
            break
    return out


def sanat_listesi():
    """İndirilmiş galeriler ve eserleri (dosyası yerinde olanlar)."""
    sd, out = os.path.join(veri_dir(), "sanat"), []
    if os.path.isdir(sd):
        for d in sorted(os.listdir(sd)):
            try:
                with open(os.path.join(sd, d, "kunye.json"), encoding="utf-8") as f:
                    k = json.load(f)
            except Exception:
                continue
            es = [x for x in k.get("eserler", []) if x.get("dosya") and os.path.exists(os.path.join(sd, d, x["dosya"]))]
            if es:
                out.append({"id": d, "baslik": k.get("baslik") or d, "kaynak": k.get("kaynak", ""), "tarih": k.get("tarih", ""), "eserler": es})
    return out


def sanat_sil(gid):
    """Galeriyi siler. Silinen bayt ya da None (öyle bir galeri yok)."""
    sd = os.path.join(veri_dir(), "sanat")
    if not gid or gid != os.path.basename(gid) or gid.startswith(".") or not os.path.isfile(os.path.join(sd, gid, "kunye.json")):
        return None
    boy = sum(b for _, _, b in veri_dosyalari(os.path.join(sd, gid)))
    shutil.rmtree(os.path.join(sd, gid), ignore_errors=True)
    d = durum_oku()
    if d.pop(gid, None) is not None:
        durum_yaz(d)
    return boy


def _oge_indir(p, vd):
    """Bir paketi indirir. Döner: durum.json'a yazılacak göreli yol ya da None."""
    tur = p["tur"]
    if tur == "kiwix":
        c = katalog_coz(p["kiwix_ad"], p.get("flavour"), {"tr": "tur", "en": "eng"}.get(p.get("dil")))
        if not c:
            log("Katalogda bulunamadı: " + p["baslik"])
            return None
        url, _, dosya = c
        isler = [(url, os.path.join("zim", dosya))]
        sonuc = "zim/" + dosya
    elif tur == "dogrudan":
        isler = [(p["url"], os.path.join("zim", p["dosya"]))]
        sonuc = "zim/" + p["dosya"]
    elif tur == "url":
        isler = [(p["url"], os.path.join(p["kategori"], p["dosya"]))]
        sonuc = p["kategori"] + "/" + p["dosya"]
    elif tur == "archive":
        with urllib.request.urlopen(urllib.request.Request("https://archive.org/metadata/" + p["arsiv_id"], headers=UA), timeout=60) as r:
            meta = json.load(r)
        uz = tuple(p.get("uzanti", [".mp3"]))
        dosyalar = [f for f in meta.get("files", []) if f.get("name", "").lower().endswith(uz)]
        if not dosyalar:
            log("Arşivde dosya yok: " + p["baslik"])
            return None
        # Arşiv her dosyanın MD5 özetini bildirir: inen dosya onunla karşılaştırılır.
        isler = [("https://archive.org/download/%s/%s" % (p["arsiv_id"], urllib.parse.quote(f["name"])),
                  os.path.join("muzik", p["id"], f["name"].replace("/", "_")), f.get("md5")) for f in dosyalar]
        sonuc = "muzik/" + p["id"]
    elif tur == "commons":
        eserler = commons_liste(p)
        if not eserler:
            log("Commons'ta kamu malı eser bulunamadı: " + p["baslik"])
            return None
        klasor = os.path.join("sanat", p["id"])
        os.makedirs(os.path.join(vd, klasor), exist_ok=True)
        with open(os.path.join(vd, klasor, "kunye.json"), "w", encoding="utf-8") as f:
            json.dump({"id": p["id"], "baslik": p["baslik"], "kaynak": "Wikimedia Commons · Category:" + p["commons_kategori"],
                       "tarih": time.strftime("%Y-%m-%d"), "eserler": [k for _, _, k in eserler]}, f, ensure_ascii=False, indent=1)
        isler = [(u, os.path.join(klasor, ad)) for u, ad, _ in eserler]
        sonuc = "sanat/" + p["id"]
    else:
        return None
    p["_dogrulandi"] = True  # bütün dosyalarının sağlaması denetlenebildi mi (durum.json'a yazılır)
    for n, is_ in enumerate(isler, 1):
        url, goreli, md5 = is_[0], is_[1], (is_[2] if len(is_) > 2 else None)
        yol = os.path.join(vd, goreli)
        if os.path.exists(yol):
            p["_dogrulandi"] = False  # önceden inmiş dosya: bu sefer denetlenmedi
            continue
        if tur == "commons":
            time.sleep(COMMONS_BEKLE)
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with IS_KILIT:
            IS["mevcut"] = p["baslik"] + (" (%d/%d)" % (n, len(isler)) if len(isler) > 1 else "")
        bozuk = 0
        for deneme in range(1, 6):
            try:
                if not dosya_indir(url, yol, md5):
                    p["_dogrulandi"] = False
                break
            except Durduruldu:
                raise
            except Bozuk as e:
                bozuk += 1
                log("%s: %s" % (p["baslik"], e))
                if bozuk >= 2:  # iki kere bozuk indiyse sorun kaynaktadır: gigabaytlarca yeniden denemenin anlamı yok
                    log("İki kere bozuk indi, eklenmedi: %s. Kaynaktaki dosya bozuk olabilir; daha sonra yeniden dene." % p["baslik"])
                    return None
                log("Baştan indiriliyor: " + p["baslik"])
            except Exception as e:
                log("Hata (%d/5): %s" % (deneme, str(e)[:90]))
                if tur == "commons" and "429" in str(e):
                    # Commons istekleri geri çeviriyor: sırayı dakikalarca tutma. İnenler durur; yeniden indirince kaldığı yerden sürer.
                    if deneme >= 2:
                        log("Wikimedia şu an istekleri geri çeviriyor; galeri yarım kaldı: %s. Daha sonra yeniden indir, kaldığı yerden sürer." % p["baslik"])
                        return None
                    time.sleep(COMMONS_CEZA)
                    continue
                time.sleep(HATA_BEKLE)
        else:
            log("İndirilemedi: " + p["baslik"])
            return None
    return sonuc


def indirme_isi():
    kalan = []
    try:
        vd = veri_dir()
        while True:
            with IS_KILIT:
                if IS["dur"] or not IS["kuyruk"]:
                    kalan = list(IS["kuyruk"]) if IS["dur"] else []
                    break
                p = IS["kuyruk"].pop(0)
                IS.update({"mevcut": p["baslik"], "yuzde": 0, "mb": 0, "hiz": 0})
                sira_kaydet([p] + IS["kuyruk"])
            log("İniyor: " + p["baslik"])
            try:
                yol = _oge_indir(p, vd)
            except Durduruldu:
                with IS_KILIT:
                    kalan = [p] + IS["kuyruk"]
                log("Duraklatıldı: %d paket bekliyor. 'Devam et' ile kaldığı yerden sürer." % len(kalan))
                break
            except Exception as e:
                log("Hata: %s — %s" % (p["baslik"], e))
                continue
            if yol:
                dogru = bool(p.pop("_dogrulandi", False))
                d = durum_oku()
                d[p["id"]] = {"yol": yol, "tarih": time.strftime("%Y-%m-%d"), "baslik": p["baslik"], "dogrulandi": dogru}
                durum_yaz(d)
                log("Tamam: " + p["baslik"] + (" (sağlaması doğrulandı)" if dogru else ""))
        kitaplari_tara()
    finally:
        with IS_KILIT:
            IS.update({"aktif": False, "mevcut": "", "yuzde": None, "kuyruk": [], "dur": False, "bekleyen": kalan})
        sira_kaydet(kalan)


def indirme_baslat(ogeler):
    with IS_KILIT:
        mevcut = {x["id"] for x in IS["kuyruk"]}
        IS["kuyruk"] += [o for o in ogeler if o["id"] not in mevcut]
        yeni = {x["id"] for x in IS["kuyruk"]}
        IS["bekleyen"] = [o for o in IS["bekleyen"] if o["id"] not in yeni]
        if IS["aktif"]:
            return
        IS.update({"aktif": True, "dur": False})
    threading.Thread(target=indirme_isi, daemon=True).start()


def yarimlari_sil():
    """Bekleyen sırayı ve yarım inmiş dosyaları siler (yer açmak için)."""
    with IS_KILIT:
        if IS["aktif"]:
            return 0
        IS["bekleyen"] = []
    sira_kaydet([])
    n = 0
    for kok, _, ds in os.walk(veri_dir()):
        for d in ds:
            if d.endswith(".yarim"):
                try:
                    os.remove(os.path.join(kok, d))
                    n += 1
                except Exception:
                    pass
    return n


def kurulu_mu(p, d, vd):
    if p["id"] in d and os.path.exists(os.path.join(vd, d[p["id"]]["yol"])):
        return True
    return False


# =====================================================================
#  NOTLAR
#  Kullanıcının maddelere yazdığı notlar veri klasöründe (notlar.json) durur: flash'a kurunca kitaplarla
#  birlikte gider. Yalnızca İmece'nin çalıştığı bilgisayardan okunur ve yazılır (ağdaki cihazlar göremez).
# =====================================================================
NOT_KILIT = threading.Lock()
NOT_AZAMI = 20000  # bir nottaki en çok harf


def notlar_oku():
    try:
        with open(os.path.join(veri_dir(), "notlar.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def not_yaz(kitap, yol, baslik, metin):
    """Notu kaydeder; metin boşsa siler. Kaydedilen kaydı (ya da boş kaydı) döner."""
    metin = str(metin or "")[:NOT_AZAMI]
    with NOT_KILIT:
        d = notlar_oku()
        anahtar = kitap + "|" + yol
        if metin.strip():
            d[anahtar] = {"kitap": kitap, "yol": yol, "baslik": str(baslik or "")[:300], "metin": metin,
                          "tarih": time.strftime("%Y-%m-%d %H:%M")}
        else:
            d.pop(anahtar, None)
        hedef = os.path.join(veri_dir(), "notlar.json")
        with open(hedef + ".yeni", "w", encoding="utf-8") as f:  # önce yan dosyaya: yazarken kesilirse eski notlar bozulmasın
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(hedef + ".yeni", hedef)
        return d.get(anahtar) or {"metin": "", "tarih": ""}


# =====================================================================
#  KÜTÜPHANEDEKİ KİTABI DENETLEME
#  "Bu dosya hâlâ sağlam mı?" (flash'a kopyaladıktan, disk sorunundan ya da yıllar sonra).
#  Büyük kitapta dakikalar sürebildiği için arka planda yapılır; arayüz ilerlemeyi sorar.
# =====================================================================
DENETIM = {}  # kitap id -> {"durum": "suruyor" | "saglam" | "bozuk" | "hata", "yuzde", "neden", "sure"}


def kitap_denetle_isi(kid, yol, st):
    t0 = time.time()
    try:
        tamam, neden = zim_saglama(yol, lambda y: st.update(yuzde=y), lambda: kid in SILINEN)  # kitap silinirse bırak
        st.update(durum="saglam" if tamam else "bozuk", neden=neden, yuzde=100, sure=round(time.time() - t0, 1))
    except Exception as e:
        st.update(durum="hata", neden=str(e), sure=round(time.time() - t0, 1))


def kitap_denetle(kid, basla):
    """Denetimin durumunu döner; basla doğruysa (ve sürmüyorsa) yeni bir denetim başlatır. Kitap yoksa None."""
    z = kitaplari_tara().get(kid)
    if not z:
        DENETIM.pop(kid, None)
        return None
    st = DENETIM.get(kid)
    if basla and not (st and st["durum"] == "suruyor"):
        st = DENETIM[kid] = {"durum": "suruyor", "yuzde": 0, "neden": "", "boyut_mb": round(os.path.getsize(z.yol) / MB)}
        threading.Thread(target=kitap_denetle_isi, args=(kid, z.yol, st), daemon=True).start()
    return dict(st) if st else {"durum": "yok"}


# =====================================================================
#  KİTAP SİLME VE DOSYADAN KİTAP EKLEME
#  İkisi de uygulamanın içinden yapılır: kullanıcı veri klasörüne elle dokunmaz.
# =====================================================================
EKLE_KILIT = threading.Lock()  # aynı anda tek kitap eklenir
EKLE_EKI = ".ekleniyor"        # kopyalanmakta olan dosya (".yarim" değil: "yarım kalanları sil" bunu silmesin)


def dizin_temizle():
    """Kitabı artık olmayan dizin dosyalarını siler (kitap silinirken dizini tam o anda yazılmış olabilir)."""
    vd = veri_dir()
    ddir = os.path.join(vd, "dizin")
    if not os.path.isdir(ddir):
        return 0
    var = {kitap_id(d) for d in os.listdir(os.path.join(vd, "zim")) if d.lower().endswith(".zim")}
    n = 0
    for d in os.listdir(ddir):
        m = re.match(r"^(.*)\.im[dt](\.yarim)?(-wal|-shm|-journal)?$", d)  # <kitap>.imd, <kitap>.imt, yarım hâli ve yan dosyaları
        if m and m.group(1) not in var:
            try:
                n += os.path.getsize(os.path.join(ddir, d))
                os.remove(os.path.join(ddir, d))
            except OSError:
                pass
    return n


def kitap_sil(kid):
    """Kitabı, dizinlerini ve kurulum kaydını siler. (silinen bayt, hata iletisi) döner; kitap yoksa (None, None)."""
    with KITAP_KILIT:
        z = KITAPLAR.pop(kid, None)
        if z is None:
            return None, None
        SILINEN.add(kid)
        DIZIN.pop(kid, None)
        DIZIN_DURUM.pop(kid, None)
        TM_DURUM.pop(kid, None)
    try:
        return _kitap_sil(kid, z)
    finally:
        SILINEN.discard(kid)


def _kitap_sil(kid, z):
    try:
        z.kapat()
    except Exception:
        pass
    boy = 0
    # Windows açık dosyayı silmez. Bu kitabın dizini tam o anda kuruluyorsa işçi kitabın listeden çıktığını
    # görüp dosyayı bırakır; o zamana kadar birkaç kere denenir.
    for deneme in range(60):
        try:
            boy = os.path.getsize(z.yol)
            os.remove(z.yol)
            break
        except FileNotFoundError:
            break
        except OSError:
            time.sleep(0.25)
    else:
        SILINEN.discard(kid)
        kitaplari_tara()  # silinemedi: kitap listede kalsın
        return 0, "Kitap dosyası şu an kullanılıyor, silinemedi. Biraz sonra yeniden dene."
    son = time.time() + 20  # bu kitabın tam metin dizini kuruluyorsa işçinin dosyalarını bırakmasını bekle
    while TM_SUREN[0] == kid and time.time() < son:
        time.sleep(0.1)
    boy += dizin_temizle()
    try:  # Paketler sekmesi "kurulu" göstermesin
        d = durum_oku()
        goreli = "zim/" + os.path.basename(z.yol)
        kalan = {k: v for k, v in d.items() if v.get("yol") != goreli}
        if len(kalan) != len(d):
            durum_yaz(kalan)
    except Exception:
        pass
    print("  kitap silindi: %s (%.0f MB)" % (kid, boy / MB), flush=True)
    return boy, None


def kitap_dosya_adi(ad):
    """Kullanıcının seçtiği dosyanın adından güvenli bir dosya adı: klasör yolu atılır, sıra dışı harfler '_' olur."""
    ad = os.path.basename(str(ad or "").replace("\\", "/"))
    if not ad.lower().endswith(".zim"):
        return None
    govde = re.sub(r"[^A-Za-z0-9_.-]", "_", ad[:-4]).strip("._")[:120]
    return (govde or "kitap") + ".zim"


def kitap_on_denetim(ad, boy, bas):
    """Kopyalamaya başlamadan önce: ad, dosyanın ilk 80 baytı, boş yer ve "zaten var mı" denetimi.
    Sorun varsa (HTTP kodu, ileti), yoksa None döner."""
    if not kitap_dosya_adi(ad):
        return 400, "Bu bir kitap dosyası değil. İmece, adı .zim ile biten kitap dosyalarını açar."
    if len(bas) < 80 or struct.unpack_from("<I", bas, 0)[0] != Zim.BUYU:
        return 400, "Bu dosya bir kitap (ZIM) dosyası değil ya da bozuk: başlığı tanınmadı."
    if boy < 96 or struct.unpack_from("<Q", bas, 72)[0] != boy - 16:
        return 400, "Dosya eksik ya da bozuk: boyutu, içinde yazan boyutla tutmuyor. Yarım inmiş ya da yarım kopyalanmış olabilir."
    imza = "%s-%d" % (bytes(bas[8:24]).hex(), boy)
    for k, z in list(kitaplari_tara().items()):
        if z.imza == imza:
            return 409, "Bu kitap zaten kütüphanende: %s" % (z.meta().get("Title") or k)
    bos = shutil.disk_usage(os.path.join(veri_dir(), "zim")).free
    if bos < boy + 200 * MB:
        return 507, "Diskte yeterli yer yok: kitap %d MB, boş yer %d MB." % (boy // MB + 1, bos // MB)
    return None


def durum_ozet(yerel=True):
    d = durum_oku()
    vd = veri_dir()
    zimler = [z for z in os.listdir(os.path.join(vd, "zim")) if z.endswith(".zim")]
    pk = paketler()
    liste = []
    for p in pk["icerikler"]:
        liste.append({k: p.get(k) for k in ("id", "baslik", "kategori", "profiller", "tahmini_mb", "lisans", "tur", "url", "not", "dil")}
                     | {"kurulu": kurulu_mu(p, d, vd), "tarih": d.get(p["id"], {}).get("tarih")})
    with IS_KILIT:
        is_ = {k: IS[k] for k in ("aktif", "mevcut", "yuzde", "mb", "hiz", "log")}
        is_["kuyruk"] = [x["baslik"] for x in IS["kuyruk"]]
        is_["bekleyen"] = [x["baslik"] for x in IS["bekleyen"]]
    # Ağdan bağlanan cihazlara bu bilgisayarın klasör yolları gösterilmez.
    return {"surum": SURUM, "yerel": yerel, "veri": vd if yerel else "", "bos_mb": round(shutil.disk_usage(vd).free / MB),
            "kategoriler": pk["kategoriler"], "paketler": liste, "is": is_,
            "zim_sayisi": len(zimler), "zimler": zimler, "zstd": zstd_ac is not None,
            "onedrive": yerel and "onedrive" in vd.lower(), "tam_metin": tm_ozet_durum(),
            # veriler başka bir diske taşınmış ve o disk takılı değilse: kütüphane boş görünür, arayüz nedenini söyler
            "veri_yok": bool(VERI_YOK[0]), "veri_yok_yol": (VERI_YOK[0] or "") if yerel else "",
            "veri_varsayilan": ayni_yol(vd, veri_varsayilan()), "tasiniyor": TASI["aktif"],
            "calisma": {"python": "%d.%d.%d" % sys.version_info[:3], "gomulu": GOMULU, "penceresiz": PENCERESIZ},
            "ag": ag_durum()}


_KATALOG_ONBELLEK = {}


def dil_katalogu(dil="tur"):
    """Açık içerik kataloğunda o dilde ne varsa hepsini listeler (1 gün önbellek)."""
    on = _KATALOG_ONBELLEK.get(dil)
    if on and time.time() - on[0] < 86400:
        return on[1]
    url = KATALOG + "?" + urllib.parse.urlencode({"lang": dil, "count": "1000"})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        kok = ET.fromstring(r.read())
    en_yeni = {}
    for e in kok.findall("a:entry", NS):
        ad = (e.findtext("a:name", "", NS) or "").strip()
        fl = (e.findtext("a:flavour", "", NS) or "").strip()
        tarih = e.findtext("a:updated", "", NS) or ""
        href, boy = None, None
        for l in e.findall("a:link", NS):
            if l.get("type") == "application/x-zim":
                href = l.get("href", "")
                href = href[:-6] if href.endswith(".meta4") else href
                boy = int(l.get("length") or 0)
        if not href:
            continue
        anahtar = ad + "|" + fl
        if anahtar in en_yeni and en_yeni[anahtar]["tarih"] >= tarih:
            continue
        en_yeni[anahtar] = {"id": "k:" + anahtar, "ad": ad, "flavour": fl, "tarih": tarih[:10],
                            "baslik": (e.findtext("a:title", "", NS) or ad).strip(),
                            "aciklama": (e.findtext("a:summary", "", NS) or "").strip(),
                            "kategori": (e.findtext("a:category", "", NS) or "").strip(),
                            "boyut_mb": round(boy / MB) if boy else None, "url": href,
                            "dosya": os.path.basename(urllib.parse.urlparse(href).path)}
    sonuc = sorted(en_yeni.values(), key=lambda x: (x["kategori"], x["baslik"]))
    _KATALOG_ONBELLEK[dil] = (time.time(), sonuc)
    return sonuc


# =====================================================================
#  FLASH DİSKE KUR
# =====================================================================
KOPYA = {"aktif": False, "yuzde": 0, "mesaj": ""}


def suruculer():
    out = []
    if os.name == "nt":
        import ctypes
        for h in string.ascii_uppercase[2:]:
            yol = h + ":\\"
            if os.path.exists(yol):
                try:
                    tur = ctypes.windll.kernel32.GetDriveTypeW(yol)
                    u = shutil.disk_usage(yol)
                    out.append({"yol": yol, "cikarilabilir": tur == 2, "bos_mb": round(u.free / MB), "toplam_mb": round(u.total / MB)})
                except Exception:
                    pass
    else:
        import glob
        for yol in glob.glob("/media/*/*") + glob.glob("/run/media/*/*") + glob.glob("/Volumes/*") + glob.glob("/mnt/*"):
            if os.path.isdir(yol) and os.path.ismount(yol):
                u = shutil.disk_usage(yol)
                out.append({"yol": yol, "cikarilabilir": True, "bos_mb": round(u.free / MB), "toplam_mb": round(u.total / MB)})
    return out


def flash_isi(hedef_kok, icerik):
    try:
        hedef = os.path.join(hedef_kok, "Imece")
        kaynaklar = []
        if getattr(sys, "frozen", False):
            kaynaklar.append((sys.executable, os.path.join(hedef, os.path.basename(sys.executable))))
        else:
            kaynaklar.append((os.path.abspath(__file__), os.path.join(hedef, "imece.py")))
        for d in os.listdir(KOK):  # açma dosyası, beni oku, belgeler: flash'ta neye tıklanacağı belli olsun
            k = os.path.join(KOK, d)
            if os.path.isfile(k) and d.lower().endswith((".bat", ".txt", ".md", ".command", ".sh")):
                kaynaklar.append((k, os.path.join(hedef, d)))
        for kok, _, dosyalar in os.walk(UYG):
            if "__pycache__" in kok:
                continue
            for d in dosyalar:
                k = os.path.join(kok, d)
                kaynaklar.append((k, os.path.join(hedef, "uygulama", os.path.relpath(k, UYG))))
        # Hazır Python da gider: flash, Python kurulu olmayan bilgisayarda da açılsın.
        for kok, altlar, dosyalar in os.walk(GOMULU_PY):
            altlar[:] = [a for a in altlar if a != "__pycache__"]
            for d in dosyalar:
                k = os.path.join(kok, d)
                kaynaklar.append((k, os.path.join(hedef, "python", os.path.relpath(k, GOMULU_PY))))
        if icerik:
            vd = veri_dir()
            for alt in ("zim", "muzik", "dizin", "sanat"):
                for kok, _, dosyalar in os.walk(os.path.join(vd, alt)):
                    for d in dosyalar:
                        if ".yarim" in d:  # yarım indirme ya da yarım dizin (yan dosyalarıyla)
                            continue
                        k = os.path.join(kok, d)
                        kaynaklar.append((k, os.path.join(hedef, "veri", os.path.relpath(k, vd))))
            for ad in ("durum.json", "notlar.json"):  # kurulum kayıtları ve kullanıcının notları
                if os.path.exists(os.path.join(vd, ad)):
                    kaynaklar.append((os.path.join(vd, ad), os.path.join(hedef, "veri", ad)))
        toplam = sum(os.path.getsize(k) for k, _ in kaynaklar) or 1
        if toplam > shutil.disk_usage(hedef_kok).free:
            KOPYA.update({"aktif": False, "mesaj": "Diskte yer yok: %d MB gerekiyor." % (toplam // MB)})
            return
        biten = 0
        for k, h in kaynaklar:
            os.makedirs(os.path.dirname(h), exist_ok=True)
            KOPYA["mesaj"] = "Kopyalanıyor: " + os.path.basename(k)
            with open(k, "rb") as fi, open(h, "wb") as fo:
                while True:
                    p = fi.read(4 * MB)
                    if not p:
                        break
                    fo.write(p)
                    biten += len(p)
                    KOPYA["yuzde"] = round(biten * 100 / toplam, 1)
        with open(os.path.join(hedef, "ayarlar.json"), "w", encoding="utf-8") as f:
            json.dump({"veri": "veri"}, f)
        KOPYA.update({"yuzde": 100, "mesaj": "Bitti: " + hedef + ". Diski güvenle çıkarabilirsin."})
    except Exception as e:
        KOPYA["mesaj"] = "Hata: %s" % e
    finally:
        KOPYA["aktif"] = False


# =====================================================================
#  VERİLERİ BAŞKA BİR DİSKE TAŞI (kitaplar, müzik, dizinler, notlar)
# =====================================================================
# Kullanıcı klasör yolu yazmaz: bir disk seçer, veriler o diskte "Imece-veri" klasörüne taşınır. Sıra: kitapları
# kapat → kopyala → kopyayı baştan okuyup aslıyla karşılaştır → ayarı değiştir → eskisini sil. Eski yer, kopyanın
# sağlam olduğu görülmeden silinmez; herhangi bir adım tutmazsa hiçbir şey değişmez.
TASI = {"aktif": False, "yuzde": 0, "mesaj": "", "hata": ""}
TASI_ADI = "Imece-veri"
TASI_ISARET = ".tasiniyor"  # yarıda kalan bir taşımanın kopyası: bir sonraki denemede üstüne yazılabilir


def veri_varsayilan():
    return os.path.join(KOK, "veri")


def ayni_yol(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def veri_dosyalari(vd):
    """Veri klasöründeki bütün dosyalar: [(tam yol, göreli yol, boy)]."""
    out = []
    for kok, _, dosyalar in os.walk(vd):
        for d in dosyalar:
            k = os.path.join(kok, d)
            try:
                out.append((k, os.path.relpath(k, vd), os.path.getsize(k)))
            except OSError:
                pass
    return out


def bos_klasorleri_sil(kok):
    for k, _, _ in os.walk(kok, topdown=False):
        try:
            os.rmdir(k)
        except OSError:
            pass


def veri_tasi_denetle(hedef):
    """Taşıma yapılabilir mi? (eski, yeni, hata) döner. hedef: bir diskin (ya da klasörün) yolu; boşsa İmece klasörü."""
    eski = veri_dir()
    if VERI_YOK[0]:
        return eski, None, "Veriler şu an takılı olmayan bir diskte duruyor (%s). Önce o diski tak, sonra İmece'yi kapatıp aç." % VERI_YOK[0]
    if hedef and not os.path.isdir(hedef):
        return eski, None, "Seçilen disk bulunamadı. Takılı olduğundan emin olup Yenile'ye bas."
    yeni = os.path.join(hedef, TASI_ADI) if hedef else veri_varsayilan()
    if ayni_yol(eski, yeni):
        return eski, yeni, "Veriler zaten orada duruyor."
    e, y = os.path.normcase(os.path.abspath(eski)) + os.sep, os.path.normcase(os.path.abspath(yeni)) + os.sep
    if e.startswith(y) or y.startswith(e):
        return eski, yeni, "Yeni yer şimdiki veri klasörüyle iç içe; oraya taşınamaz."
    with IS_KILIT:
        iniyor = IS["aktif"]
    if iniyor:
        return eski, yeni, "İndirme sürerken taşınamaz. İndirmenin bitmesini bekle ya da duraklat."
    if KOPYA["aktif"] or TASI["aktif"] or EKLE_KILIT.locked():
        return eski, yeni, "Şu an başka bir kopyalama sürüyor. Bitince yeniden dene."
    if os.path.isdir(yeni) and not os.path.exists(os.path.join(yeni, TASI_ISARET)) \
            and any(dosyalar for _, _, dosyalar in os.walk(yeni)):
        return eski, yeni, "Orada zaten içi dolu bir “%s” klasörü var. Üstüne yazmamak için taşınmadı." % TASI_ADI
    gerek = sum(b for _, _, b in veri_dosyalari(eski))
    try:
        bos = shutil.disk_usage(hedef or KOK).free
    except OSError:
        return eski, yeni, "Seçilen diskin boş yeri okunamadı."
    if gerek + 50 * MB > bos:
        return eski, yeni, "Orada yeterli yer yok: %d MB gerekiyor, %d MB boş." % (gerek // MB + 50, bos // MB)
    return eski, yeni, None


def veri_tasi_isi(eski, yeni):
    yazilan, isaret = [], os.path.join(yeni, TASI_ISARET)
    try:
        TARAMA_DURDU[0] = True
        TASI.update({"yuzde": 0, "mesaj": "Kitaplar kapatılıyor", "hata": ""})
        with KITAP_KILIT:  # açık dosya taşınamaz: bütün kitaplar kapanır, iş bitince yeni yerlerinden açılır
            for k in list(KITAPLAR):
                z = KITAPLAR.pop(k)
                DIZIN.pop(k, None)
                DIZIN_DURUM.pop(k, None)
                TM_DURUM.pop(k, None)
                try:
                    z.kapat()
                except Exception:
                    pass
        son = time.time() + 30  # tam metin işçisi elindeki dizin dosyasını bıraksın
        while (TM_MESGUL.is_set() or TM_SUREN[0]) and time.time() < son:
            time.sleep(0.1)
        dosyalar = veri_dosyalari(eski)
        toplam = sum(b for _, _, b in dosyalar) or 1
        os.makedirs(yeni, exist_ok=True)
        with open(isaret, "w") as f:
            f.write("tasiniyor")
        biten, ozetler = 0, []
        for k, gor, _ in dosyalar:
            h = os.path.join(yeni, gor)
            os.makedirs(os.path.dirname(h), exist_ok=True)
            TASI["mesaj"] = "Kopyalanıyor: " + os.path.basename(k)
            oz = hashlib.md5()
            yazilan.append(h)
            with open(k, "rb") as fi, open(h, "wb") as fo:
                while True:
                    p = fi.read(4 * MB)
                    if not p:
                        break
                    fo.write(p)
                    oz.update(p)
                    biten += len(p)
                    TASI["yuzde"] = round(biten * 70 / toplam, 1)
                fo.flush()
                os.fsync(fo.fileno())
            ozetler.append((h, oz.digest()))
        biten = 0
        for h, beklenen in ozetler:  # kopyayı diskten baştan oku, aslıyla karşılaştır; tutmazsa eskisi silinmez
            TASI["mesaj"] = "Denetleniyor: " + os.path.basename(h)
            oz = hashlib.md5()
            with open(h, "rb") as f:
                while True:
                    p = f.read(4 * MB)
                    if not p:
                        break
                    oz.update(p)
                    biten += len(p)
                    TASI["yuzde"] = round(70 + biten * 29 / toplam, 1)
            if oz.digest() != beklenen:
                raise OSError("“%s” kopyası aslıyla aynı çıkmadı" % os.path.basename(h))
        for alt in ("zim", "muzik"):
            os.makedirs(os.path.join(yeni, alt), exist_ok=True)
        os.remove(isaret)
        a = ayar_oku()
        a["veri"] = "veri" if ayni_yol(yeni, veri_varsayilan()) else yeni
        ayar_yaz(a)
    except Exception as e:
        for h in yazilan + [isaret]:  # yarım kopyayı geri al; eski yer olduğu gibi duruyor
            try:
                os.remove(h)
            except OSError:
                pass
        bos_klasorleri_sil(yeni)
        TARAMA_DURDU[0] = False
        kitaplari_tara()
        TM_UYAN.set()
        TASI.update({"aktif": False, "mesaj": "", "hata": "Taşınamadı: %s. Hiçbir şey değişmedi; veriler eski yerinde duruyor." % e})
        return
    # Buradan sonra ayar yeni yeri gösteriyor ve kopya doğrulandı; eski yer artık yalnızca artıktır.
    # Silme yarıda kalırsa (İmece kapanırsa) eski yerdeki artık, ileride oraya geri taşımayı engellemesin diye işaretlenir.
    kalan, eski_isaret = 0, os.path.join(eski, TASI_ISARET)
    try:
        with open(eski_isaret, "w") as f:
            f.write("artik")
    except OSError:
        pass
    for k, _, _ in dosyalar:
        try:
            os.remove(k)
        except OSError:
            kalan += 1
    if not kalan:
        try:
            os.remove(eski_isaret)
        except OSError:
            pass
    bos_klasorleri_sil(eski)
    TARAMA_DURDU[0] = False
    n = len(kitaplari_tara())
    TM_UYAN.set()
    print("  veriler taşındı: %s → %s (%d dosya, %d MB)" % (eski, yeni, len(dosyalar), toplam // MB), flush=True)
    TASI.update({"aktif": False, "yuzde": 100, "hata": "",
                 "mesaj": "Taşındı ve sağlaması doğrulandı: %d kitap, %s. Yeni yer: %s" % (
                     n, ("%.1f GB" % (toplam / 1024 / MB)) if toplam >= 1024 * MB else "%d MB" % (toplam // MB), yeni)
                 + (" · Eski yerde %d dosya o an kullanıldığı için silinemedi (%s)." % (kalan, eski) if kalan else "")})


# =====================================================================
#  HTTP SUNUCU
# =====================================================================
# Kitap sayfalarına eklenen başlıklar ve okuyucu betiği (yazı boyutu, gece modu, yer imi için
# sayfa bilgisini arayüze iletir; ayrıntı: uygulama/okuyucu-ic.js).
ZIM_BASLIK = {"Content-Security-Policy": "sandbox allow-scripts allow-forms allow-modals allow-downloads allow-pointer-lock",
              "Vary": "Origin"}
ZIM_EK = b'<script src="/uygulama/okuyucu-ic.js?s=' + SURUM.encode() + b'"></script>'


def okuyucu_ekle(veri):
    """Okuyucu betiğini sayfanın <head> bölümünün başına ekler (ilk çizimden önce çalışsın diye)."""
    m = re.search(rb"<head[^>]*>", veri[:4096], re.I)
    if m:
        return veri[:m.end()] + ZIM_EK + veri[m.end():]
    p = veri.lower().rfind(b"</body>")
    return veri[:p] + ZIM_EK + veri[p:] if p >= 0 else veri + ZIM_EK


class Isleyici(BaseHTTPRequestHandler):
    server_version = "Imece/" + SURUM

    def log_message(self, *a):
        pass

    def yerel_mi(self):
        """İstek İmece'nin çalıştığı bilgisayardan mı geliyor? Yönetim işlemleri (indirme, ayar,
        flash) sadece buradan yapılır. Host denetimi, alan adı oyunlarını (DNS rebinding) keser."""
        if self.client_address[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return False
        host = (self.headers.get("Host") or "").lower()
        host = host[:host.rindex(":")] if ":" in host and not host.endswith("]") else host
        if host.strip("[]") not in ("127.0.0.1", "localhost", "::1"):
            return False
        o = self.headers.get("Origin")
        return not o or bool(re.match(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", o))

    def gonder(self, kod, govde, tur="application/json; charset=utf-8", ek=None):
        if isinstance(govde, (dict, list)):
            govde = json.dumps(govde, ensure_ascii=False).encode("utf-8")
        elif isinstance(govde, str):
            govde = govde.encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        for k, v in (ek or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(govde)

    def yonlendir(self, yer):
        self.send_response(302)
        self.send_header("Location", yer)
        self.end_headers()

    def govde_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def govde_bosalt(self, sinir=65536):
        """Reddedilen bir isteğin (küçük) gövdesini okuyup atar. Okunmamış veri dururken bağlantı kapanırsa Windows
        yanıtı da düşürebiliyor; istemci o zaman "izin yok" yerine "bağlantı koptu" görüyor. Büyük gövde okunmaz."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if 0 < n <= sinir:
                self.rfile.read(n)
        except (ValueError, OSError):
            pass

    def dosya_gonder(self, kok, goreli):
        yol = os.path.normpath(os.path.join(kok, goreli))
        if not yol.startswith(os.path.normpath(kok)) or not os.path.isfile(yol):
            return self.gonder(404, "Bulunamadı", "text/plain; charset=utf-8")
        tur = mimetypes.guess_type(yol)[0] or "application/octet-stream"
        if tur.startswith("text/") or tur.endswith("javascript") or tur.endswith("json"):
            tur += "; charset=utf-8"
        boy = os.path.getsize(yol)
        rng = self.headers.get("Range")
        with open(yol, "rb") as f:
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                a = int(a or 0)
                b = int(b) if b else boy - 1
                f.seek(a)
                veri = f.read(b - a + 1)
                self.send_response(206)
                self.send_header("Content-Range", "bytes %d-%d/%d" % (a, b, boy))
            else:
                veri = f.read()
                self.send_response(200)
        self.send_header("Content-Type", tur)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(veri)))
        if kok == UYG:  # arayüz dosyaları: yeni sürüm kurulunca tarayıcı eskisini göstermesin
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(veri)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        yol = urllib.parse.unquote(u.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if yol in ("/", ""):
                return self.yonlendir("/uygulama/index.html")
            if yol.startswith("/uygulama/"):
                return self.dosya_gonder(UYG, yol[len("/uygulama/"):])
            if yol.startswith("/veri/muzik/"):
                return self.dosya_gonder(os.path.join(veri_dir(), "muzik"), yol[len("/veri/muzik/"):])
            if yol.startswith("/veri/sanat/"):
                return self.dosya_gonder(os.path.join(veri_dir(), "sanat"), yol[len("/veri/sanat/"):])
            if yol == "/api/sanat":  # indirilmiş resim galerileri
                return self.gonder(200, sanat_listesi())
            def sayi(ad, varsayilan, en_cok):
                try:
                    return max(0, min(int((q.get(ad) or [varsayilan])[0]), en_cok))
                except ValueError:
                    return varsayilan

            if yol == "/api/durum":
                return self.gonder(200, durum_ozet(self.yerel_mi()))
            if yol == "/api/kitaplar":
                return self.gonder(200, kitap_listesi())
            if yol == "/api/kitap":
                o = kitap_ozet((q.get("k") or [""])[0])
                if o:
                    o["yerel"] = self.yerel_mi()  # silme düğmesi yalnızca bu bilgisayarda görünür
                return self.gonder(200, o) if o else self.gonder(404, {"hata": "Kitap yok"})
            if yol == "/api/ara":
                s = (q.get("q") or [""])[0]
                hedef = (q.get("k") or [None])[0]
                adet = sayi("adet", 30 if hedef else 8, 300)
                sonuc = []
                for k, z in kitaplari_tara().items():
                    if hedef and k != hedef:
                        continue
                    try:
                        for r in kitapta_ara(k, z, s, adet):
                            sonuc.append(r | {"kitap": k, "kitap_baslik": z.meta().get("Title", k)})
                    except Exception as e:
                        print("arama hatası", k, e)
                sonuc.sort(key=lambda r: r.get("s", 1))  # kitaplar arası: önce adı tam tutanlar, sonra başında geçenler
                return self.gonder(200, sonuc)
            if yol == "/api/kitap-dosya":  # kitabın dosyası: başka bir İmece buradan kopyalar (kaldığı yerden sürdürebilir)
                z = kitaplari_tara().get((q.get("k") or [""])[0])
                if not z:
                    return self.gonder(404, {"hata": "Kitap yok"})
                return self.ham_dosya_gonder(z.yol)
            if yol == "/api/komsu":  # başka bir İmece'nin kitap listesi (yalnızca bu bilgisayardan sorulur)
                if not self.yerel_mi():
                    return self.gonder(403, {"hata": "Bu işlem sadece İmece'nin çalıştığı bilgisayardan yapılabilir."})
                adres = komsu_adres((q.get("adres") or [""])[0])
                if not adres:
                    return self.gonder(400, {"hata": "Adres tanınmadı. Öbür bilgisayarın gösterdiği adresi yaz; örnek: 192.168.1.8:8642"})
                liste, hata = komsu_kitaplar(adres)
                return self.gonder(502, {"hata": hata}) if hata else self.gonder(200, {"adres": adres, "kitaplar": liste})
            if yol in ("/api/notlar", "/api/not"):  # kullanıcının notları: yalnızca bu bilgisayardan görülür
                if not self.yerel_mi():
                    return self.gonder(403, {"hata": "Notlar sadece İmece'nin çalıştığı bilgisayardan görülür."})
                d = notlar_oku()
                if yol == "/api/not":
                    return self.gonder(200, d.get((q.get("k") or [""])[0] + "|" + (q.get("yol") or [""])[0]) or {"metin": "", "tarih": ""})
                var = kitaplari_tara()
                return self.gonder(200, sorted(({**n, "var": n.get("kitap") in var} for n in d.values()), key=lambda n: n.get("tarih", ""), reverse=True))
            if yol == "/api/kitap-denetle":  # kitap dosyası sağlam mı (basla=1: denetimi başlat; yalnızca bu bilgisayardan)
                basla = (q.get("basla") or [""])[0] == "1"
                if basla and not self.yerel_mi():
                    return self.gonder(403, {"hata": "Bu işlem sadece İmece'nin çalıştığı bilgisayardan yapılabilir."})
                st = kitap_denetle((q.get("k") or [""])[0], basla)
                return self.gonder(200, st) if st else self.gonder(404, {"hata": "Kitap yok"})
            if yol == "/api/metin-ara":  # maddelerin yazısının içinde arama (tam metin)
                s = (q.get("q") or [""])[0]
                hedef = (q.get("k") or [None])[0]
                adet = sayi("adet", 20 if hedef else 12, 100) or 12
                bas = sayi("bas", 0, 100000) if hedef else 0
                sonuc, devam, bekleyen = [], False, []
                for k, z in kitaplari_tara().items():
                    if hedef and k != hedef:
                        continue
                    st = TM_DURUM.get(k) or {"durum": "yok"}
                    if st["durum"] != "hazir":
                        bekleyen.append({"kitap": k, "kitap_baslik": z.meta().get("Title", k), "durum": st["durum"],
                                         "yuzde": st.get("yuzde", 0), "neden": st.get("neden", "")})
                        continue
                    try:
                        r, d2, tumu = tm_ara(k, z, s, adet if hedef else 6, bas)
                        devam = devam or d2
                        for x in r:
                            sonuc.append(x | {"kitap": k, "kitap_baslik": z.meta().get("Title", k), "tumu": tumu})
                    except Exception as e:
                        print("tam metin arama hatası", k, e, flush=True)
                if not hedef:
                    # Birkaç kitap: bütün kelimeleri içerenler öne; sonra kitabın kendi puanına göre.
                    if any(x["tumu"] for x in sonuc):
                        sonuc = [x for x in sonuc if x["tumu"]]
                    sonuc.sort(key=lambda x: x["puan"])
                    devam = devam or len(sonuc) > adet
                    sonuc = sonuc[:adet]
                return self.gonder(200, {"sonuc": sonuc, "devam": devam, "tumu": all(x["tumu"] for x in sonuc),
                                         "bekleyen": bekleyen, "acik": tm_acik(), "var": TM_VAR})
            if yol in ("/api/dizin", "/api/bolum"):
                k = (q.get("k") or [""])[0]
                z = kitaplari_tara().get(k)
                if not z:
                    return self.gonder(404, {"hata": "Kitap yok"})
                d, bas, adet = DIZIN.get(k), sayi("bas", 0, 1 << 31), sayi("adet", 200, 500) or 200
                if yol == "/api/bolum":
                    ad = (q.get("ad") or [""])[0]
                    if not d or not ad:
                        return self.gonder(200, {"liste": [], "sonraki": None, "toplam": 0})
                    lst, sonraki = d.onekle(z, ad, bas, adet)
                    toplam = next((b["adet"] for b in d.bolum if b["anahtar"] == duz(ad)), None)
                    return self.gonder(200, {"liste": lst, "sonraki": sonraki, "toplam": toplam})
                harf = (q.get("harf") or ["A"])[0]
                if harf not in HARFLER:
                    return self.gonder(400, {"hata": "Böyle bir harf yok"})
                lst, sonraki, toplam = d.liste(z, harf, bas, adet) if d else z.sade_dizin(harf, bas, adet)
                return self.gonder(200, {"liste": lst, "sonraki": sonraki, "toplam": toplam, "sirali": d is not None})
            if yol == "/api/rastgele":
                kl = kitaplari_tara()
                k = (q.get("k") or [""])[0]
                if k not in kl:
                    if not kl:
                        return self.gonder(404, {"hata": "Kitap yok"})
                    k = random.choice(list(kl))
                m = DIZIN[k].rastgele(kl[k]) if k in DIZIN else None
                return self.gonder(200, {"kitap": k, "yol": m["yol"] if m else kl[k].rastgele()})
            if yol == "/api/muzik":
                md = os.path.join(veri_dir(), "muzik")
                lst = []
                for kok, _, ds in os.walk(md):
                    for d in sorted(ds):
                        if d.lower().endswith((".mp3", ".ogg", ".opus", ".m4a", ".wav", ".flac")):
                            lst.append(os.path.relpath(os.path.join(kok, d), md).replace("\\", "/"))
                return self.gonder(200, lst)
            if yol == "/api/katalog":
                dil = (q.get("dil") or ["tur"])[0]
                try:
                    lst = dil_katalogu(dil if dil in ("tur", "eng") else "tur")
                except Exception as e:
                    return self.gonder(503, {"hata": "Kataloğa ulaşılamadı (internet var mı?): %s" % e})
                d, vd = durum_oku(), veri_dir()
                zimler = set(os.listdir(os.path.join(vd, "zim")))
                return self.gonder(200, [x | {"kurulu": x["dosya"] in zimler or x["id"] in d} for x in lst])
            if yol == "/api/suruculer":
                return self.gonder(200, suruculer() if self.yerel_mi() else [])
            if yol == "/api/flash":
                return self.gonder(200, KOPYA if self.yerel_mi() else {"aktif": False, "yuzde": 0, "mesaj": ""})
            if yol == "/api/veri-tasi":  # verileri başka bir diske taşıma: durum (yalnızca bu bilgisayardan)
                if not self.yerel_mi():
                    return self.gonder(200, {"aktif": TASI["aktif"], "yuzde": TASI["yuzde"], "mesaj": "", "hata": ""})
                return self.gonder(200, dict(TASI))
            if yol.startswith("/zim/"):
                return self.zim_sayfa(yol[5:])
            return self.gonder(404, "Bulunamadı", "text/plain; charset=utf-8")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self.gonder(500, "Hata: %s" % e, "text/plain; charset=utf-8")
            except Exception:
                pass

    def zim_sayfa(self, kalan):
        parca = kalan.split("/", 1)
        kid = parca[0]
        z = kitaplari_tara().get(kid)
        if not z:
            return self.gonder(404, "Kitap bulunamadı", "text/plain; charset=utf-8")
        if len(parca) == 1 or parca[1] == "":
            ana = z.ana_sayfa_url()
            return self.yonlendir("/zim/%s/%s" % (kid, urllib.parse.quote(ana))) if ana else self.gonder(404, "Ana sayfa yok", "text/plain")
        ic = parca[1]
        ns, _, url = ic.partition("/")
        i = z.find(ns, url)
        if i is None and ns not in ("C", "A", "I", "-", "M", "W", "X"):  # eski biçim kısa yol
            i = z.find(z.makale_ns, ic)
            ns = z.makale_ns
        if i is None:
            return self.gonder(404, "<!doctype html><meta charset=utf-8><title>Sayfa yok</title>" + ZIM_EK.decode()
                               + "<h1>Sayfa bu pakette yok</h1><p>Bu madde indirdiğin pakete dahil edilmemiş.</p>",
                               "text/html; charset=utf-8", ZIM_BASLIK)
        g = z.giris(i)
        if "yonlendirme" in g:
            h = z.coz(i)
            return self.yonlendir("/zim/%s/%s/%s" % (kid, h["ns"], urllib.parse.quote(h["url"])))
        veri = z.icerik(g)
        tur = z.mime_adi(g)
        if tur.startswith("text/") and "charset" not in tur:
            tur += "; charset=utf-8"
        ek = {"Cache-Control": "max-age=86400"}
        if "pdf" not in tur:
            # Kitap içeriği başkasının yazdığı sayfalardır: tarayıcıda yalıtılmış (kimliksiz) çalışır,
            # böylece içindeki bir betik İmece'nin yönetim uçlarını ya da arayüzünü kullanamaz.
            ek.update(ZIM_BASLIK)
        if self.headers.get("Origin") == "null":  # yalıtılmış kitap sayfasının kendi dosyalarını (yazı tipi vb.) okuması
            ek["Access-Control-Allow-Origin"] = "null"
        if tur.startswith("text/html"):
            ek["Cache-Control"] = "no-cache"
            veri = okuyucu_ekle(veri)
        if not (tur.startswith("text/") or tur.startswith("image/") or "javascript" in tur or "css" in tur):
            ek["Content-Disposition"] = "inline; filename*=UTF-8''" + urllib.parse.quote(os.path.basename(url) or "dosya")
        self.gonder(200, veri, tur, ek)

    def ham_dosya_gonder(self, yol):
        """Büyük bir dosyayı belleğe almadan, parça parça gönderir; "Range: bytes=N-" ile kaldığı yerden sürdürmeyi destekler."""
        boy = os.path.getsize(yol)
        bas = 0
        rng = self.headers.get("Range") or ""
        m = re.match(r"^bytes=(\d+)-$", rng)
        if m:
            bas = int(m.group(1))
            if bas >= boy:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % boy)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (bas, boy - 1, boy))
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(boy - bas))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(yol, "rb") as f:
                f.seek(bas)
                while True:
                    p = f.read(MB)
                    if not p:
                        break
                    self.wfile.write(p)
        except (ConnectionError, OSError):
            pass  # alan taraf duraklattı ya da kapandı

    def kitap_ekle(self):
        """Tarayıcıdan gönderilen kitap dosyasını veri klasörüne kopyalar. Gövde dosyanın kendisidir (JSON değil).
        Kopyalarken dosyanın kendi içindeki sağlama (MD5) hesaplanır; tutmuyorsa kitap eklenmez."""
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        ad = kitap_dosya_adi((q.get("ad") or [""])[0])
        boy = int(self.headers.get("Content-Length") or 0)
        self.close_connection = True  # gövdenin tamamı okunmadan yanıt verilebilir: bağlantı yeniden kullanılmasın
        if not EKLE_KILIT.acquire(blocking=False):
            return self.gonder(409, {"hata": "Şu an başka bir kitap ekleniyor. Bitince yeniden dene."})
        gecici = None
        try:
            kalan = boy
            ilk = self.rfile.read(min(MB, kalan)) if kalan > 0 else b""
            sorun = kitap_on_denetim(ad or "", boy, ilk[:80])
            if sorun:
                return self.gonder(sorun[0], {"hata": sorun[1]})
            zdir = os.path.join(veri_dir(), "zim")
            hedef, n = os.path.join(zdir, ad), 2
            while os.path.exists(hedef) or os.path.exists(hedef + EKLE_EKI):
                hedef = os.path.join(zdir, "%s-%d.zim" % (ad[:-4], n))
                n += 1
            gecici = hedef + EKLE_EKI
            ozet, tut, p = hashlib.md5(), b"", ilk
            with open(gecici, "wb") as f:
                while True:
                    if not p:
                        raise ConnectionError("gönderim yarıda kesildi")
                    kalan -= len(p)
                    f.write(p)
                    veri = tut + p  # son 16 bayt sağlamanın kendisidir; hesaba girmez
                    ozet.update(veri[:-16])
                    tut = veri[-16:]
                    if kalan <= 0:
                        break
                    p = self.rfile.read(min(MB, kalan))
            if ozet.digest() != tut:
                os.remove(gecici)
                return self.gonder(422, {"hata": "Dosya bozuk: içindeki sağlama tutmuyor. Kopyalanırken ya da indirilirken zarar görmüş; kitap eklenmedi."})
            os.replace(gecici, hedef)
            gecici = None
            kid = kitap_id(os.path.basename(hedef))
            z = kitaplari_tara().get(kid)
            if not z:
                os.remove(hedef)
                return self.gonder(422, {"hata": "Dosya kopyalandı ama kitap olarak açılamadı; eklenmedi."})
            print("  kitap eklendi: %s (%.0f MB, sağlaması doğrulandı)" % (kid, boy / MB), flush=True)
            return self.gonder(200, {"tamam": True, "id": kid, "baslik": z.meta().get("Title") or kid,
                                     "boyut_mb": round(boy / MB, 1), "dogrulandi": True})
        except ConnectionError:
            return  # tarayıcı vazgeçti ya da kapandı: yanıt verilecek kimse yok
        finally:
            EKLE_KILIT.release()
            if gecici:
                try:
                    os.remove(gecici)
                except OSError:
                    pass

    def do_POST(self):
        yol = urllib.parse.urlparse(self.path).path
        try:
            if not self.yerel_mi():
                self.close_connection = True
                self.govde_bosalt()
                return self.gonder(403, {"hata": "Bu işlem sadece İmece'nin çalıştığı bilgisayardan yapılabilir."})
            if TASI["aktif"] and yol != "/api/kapat":  # taşıma sürerken veri klasörüne yazan hiçbir iş başlamasın
                self.close_connection = True
                self.govde_bosalt()
                return self.gonder(409, {"hata": "Veriler başka bir yere taşınıyor. Bitince yeniden dene."})
            if yol == "/api/kitap-ekle":
                return self.kitap_ekle()
            g = self.govde_json()
            if yol == "/api/kitap-ekle-denetle":  # kopyalamaya başlamadan: dosya uygun mu (ilk 80 baytı onaltılık gelir)
                try:
                    bas = bytes.fromhex(str(g.get("bas") or ""))
                except ValueError:
                    bas = b""
                sorun = kitap_on_denetim(str(g.get("ad") or ""), int(g.get("boy") or 0), bas)
                return self.gonder(sorun[0], {"hata": sorun[1]}) if sorun else self.gonder(200, {"tamam": True, "ad": kitap_dosya_adi(g.get("ad"))})
            if yol == "/api/komsu-al":  # başka bir İmece'deki kitapları indirme sırasına koy
                adres = komsu_adres(g.get("adres"))
                if not adres:
                    return self.gonder(400, {"hata": "Adres tanınmadı."})
                liste, hata = komsu_kitaplar(adres)
                if hata:
                    return self.gonder(502, {"hata": hata})
                istenen = set(g.get("ids") or [])
                ogeler = [{"id": "komsu:" + k["dosya"], "baslik": k["baslik"], "tur": "dogrudan", "dosya": k["dosya"],
                           "url": adres + "/api/kitap-dosya?k=" + urllib.parse.quote(k["id"], safe="")}
                          for k in liste if k["id"] in istenen and not k["var"]]
                indirme_baslat(ogeler)
                return self.gonder(200, {"tamam": True, "adet": len(ogeler)})
            if yol == "/api/not":  # maddeye not yaz (boş metin notu siler)
                if not g.get("kitap") or not g.get("yol"):
                    return self.gonder(400, {"hata": "Hangi sayfanın notu olduğu belli değil"})
                return self.gonder(200, not_yaz(str(g["kitap"]), str(g["yol"]), g.get("baslik"), g.get("metin")))
            if yol == "/api/ag":  # ağ paylaşımını aç ya da kapat (yalnızca bu bilgisayardan; ağdaki bir cihaz kapatamaz)
                r = ag_ac() if g.get("ac") else ag_kapat()
                return self.gonder(409 if r.get("hata") else 200, r)
            if yol == "/api/sanat-sil":
                boy = sanat_sil(str(g.get("id") or ""))
                if boy is None:
                    return self.gonder(404, {"hata": "Böyle bir galeri yok"})
                return self.gonder(200, {"tamam": True, "silinen_mb": round(boy / MB, 1)})
            if yol == "/api/kitap-sil":
                boy, hata = kitap_sil(str(g.get("k") or ""))
                if boy is None:
                    return self.gonder(404, {"hata": "Böyle bir kitap yok"})
                if hata:
                    return self.gonder(409, {"hata": hata})
                return self.gonder(200, {"tamam": True, "silinen_mb": round(boy / MB, 1)})
            if yol == "/api/devam":
                with IS_KILIT:
                    bekleyen = list(IS["bekleyen"])
                indirme_baslat(bekleyen)
                return self.gonder(200, {"tamam": True, "adet": len(bekleyen)})
            if yol == "/api/sira-sil":
                return self.gonder(200, {"tamam": True, "silinen": yarimlari_sil()})
            if yol == "/api/kapat":
                self.gonder(200, {"tamam": True})
                threading.Thread(target=kapat_isi, daemon=True).start()
                return
            if yol == "/api/indir":
                pk = paketler()["icerikler"]
                diller = set(g.get("diller") or ["tr", "en"])
                ogeler = []
                if g.get("profil"):
                    ogeler = [p for p in pk if g["profil"] in p["profiller"] and p["tur"] != "elle"
                              and (p.get("dil") in diller or p.get("dil") in (None, "mul", "-"))]
                for i in g.get("ids", []):
                    ogeler += [p for p in pk if p["id"] == i]
                if g.get("katalog"):
                    tum = {x["id"]: x for dl in ("tur", "eng") for x in _KATALOG_ONBELLEK.get(dl, (0, []))[1]}
                    for i in g["katalog"]:
                        x = tum.get(i)
                        if x:
                            ogeler.append({"id": x["id"], "baslik": x["baslik"], "tur": "dogrudan", "url": x["url"], "dosya": x["dosya"]})
                d, vd = durum_oku(), veri_dir()
                ogeler = [o for o in ogeler if not kurulu_mu(o, d, vd)]
                indirme_baslat(ogeler)
                return self.gonder(200, {"tamam": True, "adet": len(ogeler)})
            if yol == "/api/durdur":
                IS["dur"] = True
                return self.gonder(200, {"tamam": True})
            if yol == "/api/ayar":
                a = ayar_oku()
                if "veri" in g:
                    v = g["veri"].strip() or "veri"
                    tam = v if os.path.isabs(v) else os.path.join(KOK, v)
                    os.makedirs(tam, exist_ok=True)
                    try:  # İmece klasörünün içindeyse göreli sakla: klasör taşınınca (flash) bozulmasın
                        gor = os.path.relpath(tam, KOK)
                        if not gor.startswith(".."):
                            v = gor
                    except ValueError:
                        pass
                    a["veri"] = v
                if "tam_metin" in g:  # tam metin arama dizinleri kurulsun mu
                    a["tam_metin"] = bool(g["tam_metin"])
                ayar_yaz(a)
                kitaplari_tara()
                TM_UYAN.set()
                return self.gonder(200, {"tamam": True, "veri": veri_dir(), "tam_metin": tm_ozet_durum()})
            if yol == "/api/tam-metin-sil":  # dizinleri sil, yer aç; ayar da kapanır (yoksa hemen yeniden kurulurdu)
                a = ayar_oku()
                a["tam_metin"] = False
                ayar_yaz(a)
                son = time.time() + 15
                while TM_MESGUL.is_set() and time.time() < son:
                    time.sleep(0.1)
                silinen = 0
                for k, z in list(kitaplari_tara().items()):
                    silinen += tm_sil(tm_yolu(z, k)) + tm_sil(tm_yolu(z, k) + ".yarim")
                    if k in TM_DURUM:
                        TM_DURUM[k] = {"durum": "kapali", "yuzde": 0}
                return self.gonder(200, {"tamam": True, "silinen_mb": round(silinen / MB, 1), "tam_metin": tm_ozet_durum()})
            if yol == "/api/veri-tasi":  # {"hedef": disk yolu} ya da {"hedef": ""} (İmece klasörüne geri al)
                eski, yeni, hata = veri_tasi_denetle(str(g.get("hedef") or ""))
                if hata:
                    return self.gonder(409, {"hata": hata})
                TASI.update({"aktif": True, "yuzde": 0, "mesaj": "Başlıyor", "hata": ""})
                threading.Thread(target=veri_tasi_isi, args=(eski, yeni), daemon=True).start()
                return self.gonder(200, {"tamam": True, "yeni": yeni})
            if yol == "/api/flash":
                if KOPYA["aktif"] or TASI["aktif"]:
                    return self.gonder(409, {"hata": "Kopyalama sürüyor"})
                h = g.get("hedef", "")
                if not h or not os.path.isdir(h):
                    return self.gonder(400, {"hata": "Hedef disk bulunamadı"})
                KOPYA.update({"aktif": True, "yuzde": 0, "mesaj": "Başlıyor"})
                threading.Thread(target=flash_isi, args=(h, bool(g.get("icerik"))), daemon=True).start()
                return self.gonder(200, {"tamam": True})
            return self.gonder(404, {"hata": "yok"})
        except Exception as e:
            self.gonder(500, {"hata": str(e)})


def calisiyor_mu(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/durum" % port, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


SUNUCU = None


class Sunucu(ThreadingHTTPServer):
    daemon_threads = True
    # Windows'ta "adresi yeniden kullan" seçeneği, başka bir programın tuttuğu bağlantı noktasına
    # sessizce ortak olur (İmece açılmış görünür ama çalışmaz). Orada kapalı: doluysa hata verir.
    allow_reuse_address = os.name != "nt"


# =====================================================================
#  AĞ PAYLAŞIMI
#  Aynı ağdaki telefon, tablet ve bilgisayarlar kütüphaneyi okuyabilsin. Uygulamanın içinden açılıp kapanır
#  (Ayarlar). Açıkken bu bilgisayarın ağ adresinde ikinci bir dinleyici çalışır; ağdan gelenler yalnızca okur,
#  yönetim işlemleri (indirme, silme, ayar, paylaşımı kapatma) yine sadece bu bilgisayardan yapılır (yerel_mi).
#  Kalıcı değildir: İmece kapanınca paylaşım da kapanır (başka bir ağda farkında olmadan açık kalmasın).
# =====================================================================
AG = {"sunucu": None, "ip": None, "sabit": False}  # sabit: komut satırından --ag ile açıldı (uygulamadan kapatılamaz)
AG_KILIT = threading.Lock()
CALISAN_PORT = [8642]


def ag_ip():
    """Bu bilgisayarın yerel ağdaki adresi; ağa bağlı değilse None. (Hiçbir yere veri gönderilmez:
    bağlantısız bir yuva, işletim sistemine "dışarı hangi adresle çıkarım" diye sorar.)"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") or ip == "0.0.0.0" else ip


def ag_durum():
    ip = AG["ip"] if AG["sunucu"] else (ag_ip() if AG["sabit"] else None)
    acik = bool(AG["sunucu"] or AG["sabit"])
    d = {"acik": acik, "sabit": AG["sabit"], "adres": "http://%s:%d/" % (ip, CALISAN_PORT[0]) if acik and ip else ""}
    if AG["sunucu"]:
        d["ag_degisti"] = ag_ip() != AG["ip"]  # Wi-Fi değişmişse eski adres artık çalışmaz
    return d


def ag_ac():
    with AG_KILIT:
        if AG["sunucu"] or AG["sabit"]:
            return ag_durum()
        ip = ag_ip()
        if not ip:
            return {"hata": "Bu bilgisayar şu an bir ağa bağlı görünmüyor. Wi-Fi ya da kabloyla bir ağa bağlan, sonra yeniden dene."}
        try:
            s = Sunucu((ip, CALISAN_PORT[0]), Isleyici)
        except OSError as e:
            return {"hata": "Ağ adresi açılamadı (%s). Ayrıntı: %s" % (ip, e)}
        AG.update(sunucu=s, ip=ip)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        print("  ağ paylaşımı açıldı: http://%s:%d/" % (ip, CALISAN_PORT[0]), flush=True)
        return ag_durum()


def ag_kapat():
    with AG_KILIT:
        s = AG["sunucu"]
        if s:
            AG.update(sunucu=None, ip=None)
            s.shutdown()
            s.server_close()
            print("  ağ paylaşımı kapatıldı", flush=True)
        return ag_durum()


# =====================================================================
#  BAŞKA BİR İMECE'DEN KİTAP ALMA (internetsiz, bilgisayardan bilgisayara)
#  Yakındaki bir bilgisayarda İmece açık ve paylaşımı açıksa, oradaki kitaplar buraya kopyalanabilir.
#  Kopyalama, indirme yöneticisinden geçer: duraklatılabilir, kaldığı yerden sürer, sağlaması denetlenir.
# =====================================================================
def komsu_adres(metin):
    """Kullanıcının yazdığı adresi "http://a.b.c.d:port" biçimine getirir. Yalnızca yerel ağ adresleri kabul edilir
    (İmece, yazılan herhangi bir internet adresine istek atan bir araca dönüşmesin). Uygun değilse None."""
    m = re.match(r"^\s*(?:https?://)?(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?::(\d{1,5}))?(?:/.*)?\s*$", str(metin or ""))
    if not m:
        return None
    a, b, c, d = (int(x) for x in m.groups()[:4])
    port = int(m.group(5) or 8642)
    if max(a, b, c, d) > 255 or not 0 < port < 65536:
        return None
    yerel = a in (10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31) or (a == 169 and b == 254)
    return "http://%d.%d.%d.%d:%d" % (a, b, c, d, port) if yerel else None


def komsu_kitaplar(adres):
    """Öbür İmece'nin kitap listesi; her kitap için bizde olup olmadığı. (liste, hata iletisi)"""
    try:
        with urllib.request.urlopen(urllib.request.Request(adres + "/api/kitaplar", headers=UA), timeout=8) as r:
            liste = json.load(r)
        if not isinstance(liste, list):
            raise ValueError("beklenmeyen yanıt")
    except Exception as e:
        return None, ("O adreste İmece bulunamadı ya da paylaşımı kapalı. Öbür bilgisayarda Ayarlar → “Aynı ağdaki cihazlarla paylaş” "
                      "açık mı, iki bilgisayar aynı ağda mı? (Ayrıntı: %s)" % e)
    bizde = {z.imza for z in kitaplari_tara().values()}
    out = []
    for k in liste:
        if not isinstance(k, dict) or not k.get("id") or not kitap_dosya_adi(k.get("dosya")):
            continue  # eski sürüm bir İmece dosya adını bildirmez: o kitap alınamaz
        out.append({"id": str(k["id"]), "baslik": str(k.get("baslik") or k["id"]), "aciklama": str(k.get("aciklama") or ""),
                    "boyut_mb": k.get("boyut_mb"), "madde": k.get("madde"), "dosya": kitap_dosya_adi(k["dosya"]),
                    "var": k.get("imza") in bizde})
    return out, None


def kapat_isi():
    """Uygulamadaki "İmece'yi kapat" düğmesi: süren indirme varsa kaldığı yeri kaydedip durur, sonra sunucu kapanır."""
    IS["dur"] = True
    TM_DUR.set()  # süren tam metin dizini en yakın kayıt noktasında durur; açılışta kaldığı yerden sürer
    son = time.time() + 8
    while (IS["aktif"] or TM_MESGUL.is_set()) and time.time() < son:
        time.sleep(0.1)
    try:
        ag_kapat()
    except Exception:
        pass
    print("  Kapatma istendi, İmece kapanıyor.", flush=True)
    if SUNUCU:
        SUNUCU.shutdown()


def main():
    global SUNUCU
    if PENCERESIZ:
        gunluk_ac()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="İmece")
    p.add_argument("--port", type=int, default=8642)
    p.add_argument("--ag", action="store_true", help="Aynı ağdaki cihazlara aç (Pi kutusu)")
    p.add_argument("--tarayici-acma", action="store_true")
    a = p.parse_args()
    adres = "http://127.0.0.1:%d/" % a.port
    if calisiyor_mu(a.port):
        if not a.tarayici_acma:
            webbrowser.open(adres)
        return
    try:
        sunucu = Sunucu(("0.0.0.0" if a.ag else "127.0.0.1", a.port), Isleyici)
    except OSError as e:
        hata_goster("İmece açılamadı.\n\nBu bilgisayarda başka bir program İmece'nin kullandığı bağlantı noktasını "
                    "(%d) tutuyor. Bilgisayarı yeniden başlatıp bir daha dene.\n\nAyrıntı: %s" % (a.port, e))
        sys.exit(1)
    SUNUCU = sunucu
    CALISAN_PORT[0] = a.port
    AG["sabit"] = bool(a.ag)
    print("=" * 52)
    print("  İMECE %s çalışıyor" % SURUM)
    print("  Adres: " + adres)
    if a.ag:
        print("  Ağdaki cihazlar için: " + (ag_durum()["adres"] or "(bu bilgisayar bir ağa bağlı değil)"))
    print("  Python %s (%s)" % (sys.version.split()[0], "klasördeki hazır Python" if GOMULU else "bilgisayarda kurulu Python"))
    print("  Kapatmak için uygulamadaki \"İmece'yi kapat\" düğmesine bas." if PENCERESIZ else "  Bu pencereyi kapatırsan İmece kapanır.")
    print("=" * 52, flush=True)
    vd = veri_dir()
    for d in os.listdir(os.path.join(vd, "zim")):  # yarıda kalmış "dosyadan kitap ekle" kopyaları
        if d.endswith(EKLE_EKI):
            try:
                os.remove(os.path.join(vd, "zim", d))
            except OSError:
                pass
    sira_yukle()
    threading.Thread(target=dizin_isi, daemon=True).start()
    threading.Thread(target=tam_metin_isi, daemon=True).start()
    kitaplari_tara()
    dizin_temizle()  # kitabı artık olmayan dizin dosyaları (elle silinmiş kitaplar, yarıda kalmış temizlikler)
    if not a.tarayici_acma:
        threading.Timer(0.6, lambda: webbrowser.open(adres)).start()
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        pass
    sunucu.server_close()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        ayrinti = traceback.format_exc()
        if PENCERESIZ and not GUNLUK:
            gunluk_ac()
        print(ayrinti, flush=True)
        hata_goster("İmece beklenmedik bir hatayla kapandı.\n\n%s%s" % (
            ayrinti.strip().splitlines()[-1], "\n\nAyrıntılar şu dosyada: " + GUNLUK if GUNLUK else ""))
        sys.exit(1)
