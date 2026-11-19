"""İmece açılış senaryoları (Windows): kurulu Python olmadan, klasördeki hazır Python ile açılış.

Kullanım (klasördeki Python ile de çalışır, başka bir şey gerekmez):
  python\\python.exe gelistirme\\test\\acilis.py <imece klasörü> [--port 8660]
        [--resmi-zip python-3.14.6-embed-amd64.zip] [--paket imece-0.8-windows.zip] [--json çıktı.json]

Her senaryo, PATH'inde Python bulunmayan bir ortamda (yalnızca Windows'un kendi klasörleri) çalıştırılır.
"""
import argparse, ctypes, filecmp, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.request, zipfile
from ctypes import wintypes

ap = argparse.ArgumentParser()
ap.add_argument("klasor")
ap.add_argument("--port", type=int, default=8660)
ap.add_argument("--resmi-zip")
ap.add_argument("--paket")
ap.add_argument("--json")
A = ap.parse_args()
A.klasor = os.path.abspath(A.klasor)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

WIN = os.environ.get("SystemRoot", r"C:\Windows")
PS = os.path.join(WIN, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
# Python'suz ortam: PATH'te yalnızca Windows'un kendi klasörleri var; Python ile ilgili değişkenler yok.
ORTAM = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "PY_", "VIRTUAL_ENV", "CONDA"))}
ORTAM["PATH"] = os.path.join(WIN, "System32") + ";" + WIN
SONUC = []
k32, u32 = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("user32", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
k32.CloseHandle.argtypes = (wintypes.HANDLE,)
k32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))


def senaryo(kod, ad):
    def sar(f):
        t0 = time.time()
        try:
            gecti, kanit = f()
        except Exception as e:
            gecti, kanit = False, "HATA: %s: %s" % (type(e).__name__, e)
        SONUC.append({"kod": kod, "ad": ad, "durum": "GEÇTİ" if gecti else "KALDI", "kanit": kanit, "sure": round(time.time() - t0, 1)})
        print("[%s] %s  %s\n       %s" % (SONUC[-1]["durum"], kod, ad, kanit), flush=True)
        return f
    return sar


def durum(port, zaman=2):
    with urllib.request.urlopen("http://127.0.0.1:%d/api/durum" % port, timeout=zaman) as r:
        return json.load(r)


def gonder(port, yol, basliklar=None):
    ist = urllib.request.Request("http://127.0.0.1:%d%s" % (port, yol), data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", **(basliklar or {})})
    try:
        with urllib.request.urlopen(ist, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def ayakta_bekle(port, sn=30):
    son = time.time() + sn
    while time.time() < son:
        try:
            return durum(port)
        except Exception:
            time.sleep(0.25)
    return None


def dinleyen_pid(port):
    c = subprocess.run([os.path.join(WIN, "System32", "netstat.exe"), "-ano", "-p", "TCP"], capture_output=True, text=True, errors="replace").stdout
    for s in c.splitlines():
        p = s.split()
        if len(p) >= 5 and p[1].endswith(":%d" % port) and p[3].upper() == "LISTENING":
            return int(p[4])
    return 0


def surec_yolu(pid):
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return ""
    try:
        tampon, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        return tampon.value if k32.QueryFullProcessImageNameW(h, 0, tampon, ctypes.byref(n)) else ""
    finally:
        k32.CloseHandle(h)


def bitti_bekle(pid, sn=15):
    h = k32.OpenProcess(0x100000, False, pid)
    if not h:
        return True
    try:
        return k32.WaitForSingleObject(h, int(sn * 1000)) == 0
    finally:
        k32.CloseHandle(h)


def pencereler(pid):
    """Sürecin görünür pencereleri: [(başlık, [içindeki yazılar])]."""
    out = []
    TUR = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def yazi(h):
        t = ctypes.create_unicode_buffer(2048)
        u32.GetWindowTextW(h, t, 2048)
        return t.value

    def her(h, _):
        sahip = wintypes.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(sahip))
        if sahip.value == pid and u32.IsWindowVisible(h):
            ic = []
            u32.EnumChildWindows(h, TUR(lambda c, __: ic.append(yazi(c)) or True), 0)
            out.append((yazi(h), [x for x in ic if x]))
        return True
    u32.EnumWindows(TUR(her), 0)
    return out


def oldur(pid):
    subprocess.run([os.path.join(WIN, "System32", "taskkill.exe"), "/F", "/PID", str(pid)], capture_output=True)


def bat_calistir(klasor, port, sn=30):
    """Imece-Ac.bat'ı Python'suz ortamda, başka bir klasörden (çift tıklamada olduğu gibi) çalıştırır."""
    t0 = time.time()
    c = subprocess.run([os.path.join(WIN, "System32", "cmd.exe"), "/c", os.path.join(klasor, "Imece-Ac.bat"), "--port", str(port), "--tarayici-acma"],
                       env=ORTAM, cwd=tempfile.gettempdir(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=sn)
    return c.returncode, time.time() - t0


def kapat_ve_bekle(port):
    pid = dinleyen_pid(port)
    try:
        gonder(port, "/api/kapat")
    except Exception:
        pass
    if pid and not bitti_bekle(pid, 15):
        oldur(pid)
        return False
    return True


def kisa(yol):
    return yol[len(os.path.dirname(A.klasor)) + 1:] if yol.lower().startswith(os.path.dirname(A.klasor).lower()) else yol


PY = os.path.join(A.klasor, "python")
PORT = A.port


@senaryo("B1", "Klasördeki Python resmi ve değiştirilmemiş: bütün çalıştırılabilir dosyalar dijital imzalı")
def _():
    komut = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-ChildItem -LiteralPath '%s' -File | Where-Object { $_.Extension -in '.exe','.dll','.pyd' } | "
             "ForEach-Object { $s = Get-AuthenticodeSignature -LiteralPath $_.FullName; '{0}|{1}|{2}' -f $_.Name, $s.Status, $s.SignerCertificate.Subject }") % PY.replace("'", "''")
    c = subprocess.run([PS, "-NoProfile", "-NonInteractive", "-Command", komut], capture_output=True, timeout=180)
    satir = [s.split("|", 2) for s in c.stdout.decode("utf-8", "replace").splitlines() if "|" in s]
    kotu = [s[0] for s in satir if s[1] != "Valid" or not ("CN=Python Software Foundation" in s[2] or "CN=Microsoft" in s[2])]
    psf = len([1 for s in satir if "Python Software Foundation" in s[2]])
    ek = ""
    ayni = True
    if A.resmi_zip:
        with zipfile.ZipFile(A.resmi_zip) as z:
            adlar = [i.filename for i in z.infolist() if not i.is_dir()]
            farkli = [a for a in adlar if not os.path.exists(os.path.join(PY, a)) or open(os.path.join(PY, a), "rb").read() != z.read(a)]
        fazla = [os.path.relpath(os.path.join(k, d), PY) for k, _a, ds in os.walk(PY) for d in ds if os.path.relpath(os.path.join(k, d), PY).replace(os.sep, "/") not in adlar]
        ayni = not farkli and not fazla
        ek = " | python.org'dan inen zip ile karşılaştırma: %d dosyanın %d'i bayt bayt aynı, fazladan dosya: %s" % (len(adlar), len(adlar) - len(farkli), fazla or "yok")
    return bool(satir) and not kotu and ayni, "%d imzalı dosya (%d'i Python Software Foundation, %d'i Microsoft), imzası geçersiz: %s%s" % (
        len(satir), psf, len(satir) - psf, kotu or "yok", ek)


@senaryo("B2", "Hazır Python'da İmece'nin ihtiyacı olan her şey var ve bilgisayardaki başka Python'a bakmıyor")
def _():
    kod = ("import sys, lzma, ssl, ctypes, sqlite3, unicodedata, xml.etree.ElementTree, compression.zstd as z\n"
           "c = sqlite3.connect(':memory:'); c.execute('create virtual table t using fts5(a)')\n"
           "import json; print(json.dumps({'surum': sys.version.split()[0], 'yol': sys.path, 'sqlite': sqlite3.sqlite_version, 'ssl': ssl.OPENSSL_VERSION, 'zstd': len(z.compress(b'x' * 99))}))")
    c = subprocess.run([os.path.join(PY, "python.exe"), "-c", kod], env=ORTAM, capture_output=True, text=True, timeout=60)
    if c.returncode:
        return False, "çalışmadı: " + c.stderr.strip()[-300:]
    b = json.loads(c.stdout)
    disari = [y for y in b["yol"] if not os.path.normcase(os.path.abspath(y)).startswith(os.path.normcase(PY))]
    return not disari, "Python %s | zstd, xz, SQLite %s (tam metin arama için FTS5 dahil), %s hazır | modül arama yolu yalnızca klasörün içi: %s" % (
        b["surum"], b["sqlite"], b["ssl"], "evet" if not disari else "HAYIR: %s" % disari)


@senaryo("B3", "PATH'te Python yokken Imece-Ac.bat İmece'yi açıyor")
def _():
    var = [n for n in ("py", "python", "python3") if subprocess.run([os.path.join(WIN, "System32", "where.exe"), n], env=ORTAM, capture_output=True).returncode == 0]
    kod, sure = bat_calistir(A.klasor, PORT)
    d = ayakta_bekle(PORT, 40)
    if not d:
        return False, "bat çıkış kodu %s, sunucu 40 sn içinde ayağa kalkmadı (ortamda bulunan Python komutu: %s)" % (kod, var or "yok")
    c = d.get("calisma", {})
    return kod == 0 and not var and c.get("gomulu") and c.get("penceresiz"), "ortamda Python komutu: %s | bat %.1f sn'de bitti (çıkış %d) | İmece %s, Python %s, klasördeki Python ile: %s, penceresiz: %s | %d kitap" % (
        var or "yok", sure, kod, d["surum"], c.get("python"), c.get("gomulu"), c.get("penceresiz"), d["zim_sayisi"])


@senaryo("B4", "Siyah pencere kalmıyor: çalışan süreç klasördeki pythonw, görünür penceresi yok")
def _():
    pid = dinleyen_pid(PORT)
    yol = surec_yolu(pid)
    pen = pencereler(pid)
    return os.path.normcase(yol) == os.path.normcase(os.path.join(PY, "pythonw.exe")) and not pen, "süreç: %s | görünür pencere: %s" % (kisa(yol), pen or "yok")


@senaryo("B5", "İkinci kez çift tıklamak ikinci bir İmece başlatmıyor")
def _():
    pid = dinleyen_pid(PORT)
    kod, sure = bat_calistir(A.klasor, PORT)
    time.sleep(3)
    komut = "(Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq '%s' } | Measure-Object).Count" % os.path.join(PY, "pythonw.exe").replace("'", "''")
    n = subprocess.run([PS, "-NoProfile", "-NonInteractive", "-Command", komut], capture_output=True, text=True, timeout=60).stdout.strip()
    return kod == 0 and dinleyen_pid(PORT) == pid and n == "1", "bat çıkış %d | dinleyen süreç aynı: %s | bu klasörden çalışan pythonw sayısı: %s" % (kod, dinleyen_pid(PORT) == pid, n)


@senaryo("B6", "Kapatma ucu dışarıdaki bir sitenin isteğini reddediyor")
def _():
    a = gonder(PORT, "/api/kapat", {"Origin": "http://kotu.example"})
    b = gonder(PORT, "/api/kapat", {"Host": "kotu.example:%d" % PORT})
    time.sleep(1)
    return a == 403 and b == 403 and ayakta_bekle(PORT, 3) is not None, "yabancı Origin: %d | yabancı Host: %d | İmece hâlâ çalışıyor: %s" % (a, b, ayakta_bekle(PORT, 3) is not None)


@senaryo("B7", "Flash'a kur: hazır Python da kopyalanıyor; kopya, Python'suz ortamda kendi bat'ıyla açılıyor ve kapanıyor")
def _():
    gecici = tempfile.mkdtemp(prefix="imece-flash-")
    try:
        ist = urllib.request.Request("http://127.0.0.1:%d/api/flash" % PORT, data=json.dumps({"hedef": gecici, "icerik": False}).encode(), method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(ist, timeout=10).read()
        for _i in range(240):
            with urllib.request.urlopen("http://127.0.0.1:%d/api/flash" % PORT, timeout=10) as r:
                k = json.load(r)
            if not k["aktif"]:
                break
            time.sleep(0.5)
        kopya = os.path.join(gecici, "Imece")
        ks = filecmp.dircmp(PY, os.path.join(kopya, "python"))
        eksik = ks.left_only + ks.diff_files + ks.funny_files
        ust = sorted(os.listdir(kopya))
        kod, sure = bat_calistir(kopya, PORT + 1)
        d = ayakta_bekle(PORT + 1, 40)
        yol = surec_yolu(dinleyen_pid(PORT + 1)) if d else ""
        kapandi = kapat_ve_bekle(PORT + 1) if d else False
        tamam = (not eksik and d and d["calisma"]["gomulu"] and os.path.normcase(yol) == os.path.normcase(os.path.join(kopya, "python", "pythonw.exe")) and kapandi)
        return bool(tamam), "%s | kopyadaki üst düzey: %s | python klasöründe eksik/farklı: %s (%d dosya aynı) | kopya açıldı: %s (kendi pythonw'siyle: %s) | kapandı: %s" % (
            k["mesaj"].split(":")[0], ", ".join(ust), eksik or "yok", len(ks.same_files), bool(d), bool(yol) and "Imece\\python\\pythonw.exe" in yol, kapandi)
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


@senaryo("B8", "\"İmece'yi kapat\": sunucu kapanıyor, süreç bitiyor, bağlantı noktası boşalıyor")
def _():
    pid = dinleyen_pid(PORT)
    kod = gonder(PORT, "/api/kapat")
    t0 = time.time()
    bitti = bitti_bekle(pid, 15)
    sure = time.time() - t0
    time.sleep(0.5)
    bos = dinleyen_pid(PORT) == 0
    gunluk = ""
    try:
        gunluk = open(os.path.join(A.klasor, "imece-gunluk.log"), encoding="utf-8").read()
    except OSError:
        pass
    if not bitti:
        oldur(pid)
    return kod == 200 and bitti and bos and "Kapatma istendi" in gunluk, "yanıt %d | süreç %.1f sn'de bitti: %s | bağlantı noktası boş: %s | günlükte kapanış kaydı: %s" % (
        kod, sure, bitti, bos, "Kapatma istendi" in gunluk)


@senaryo("B9", "Bağlantı noktası başka programdayken sessizce ölmüyor: anlaşılır bir ileti kutusu çıkıyor")
def _():
    s = socket.socket()
    s.bind(("127.0.0.1", PORT + 2))
    s.listen(1)
    p = subprocess.Popen([os.path.join(PY, "pythonw.exe"), os.path.join(A.klasor, "imece.py"), "--port", str(PORT + 2), "--tarayici-acma"],
                         env=ORTAM, cwd=A.klasor, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        pen = []
        son = time.time() + 20
        while time.time() < son and not pen and p.poll() is None:
            time.sleep(0.5)
            pen = pencereler(p.pid)
        yazi = " ".join(" ".join(ic) for _b, ic in pen).replace("\n", " ")
        return bool(pen) and pen[0][0] == "İmece" and "İmece açılamadı" in yazi and str(PORT + 2) in yazi, "ileti kutusu: %s | başlık: %s | yazı: %s" % (
            "çıktı" if pen else "ÇIKMADI (süreç çıkış kodu %s)" % p.poll(), pen[0][0] if pen else "-", yazi[:170] or "-")
    finally:
        p.kill()
        s.close()


@senaryo("B10", "İndirilen zip, boşluklu ve Türkçe harfli bir klasöre çıkarılınca Python'suz ortamda açılıyor")
def _():
    if not A.paket:
        return False, "paket verilmedi (--paket)"
    gecici = tempfile.mkdtemp(prefix="imece-zip-")
    hedef = os.path.join(gecici, "İmece deneme klasörü (ğüşiöç)")
    try:
        with zipfile.ZipFile(A.paket) as z:
            z.extractall(hedef)
            n = len(z.namelist())
        kok = os.path.join(hedef, "imece")
        oku = [d for d in os.listdir(kok) if d.startswith("BEN")]
        kod, sure = bat_calistir(kok, PORT + 3)
        d = ayakta_bekle(PORT + 3, 40)
        with urllib.request.urlopen("http://127.0.0.1:%d/" % (PORT + 3), timeout=10) as r:
            sayfa = r.read().decode("utf-8")
        yol = surec_yolu(dinleyen_pid(PORT + 3)) if d else ""
        kapandi = kapat_ve_bekle(PORT + 3) if d else False
        tamam = d and d["calisma"]["gomulu"] and d["calisma"]["penceresiz"] and ("Sürüm " + d["surum"]) in sayfa and oku == ["BENİ OKU.txt"] and kapandi \
            and os.path.normcase(yol) == os.path.normcase(os.path.join(kok, "python", "pythonw.exe"))
        return bool(tamam), "%d dosya çıkarıldı (%d MB) | %s | açıldı: %s, İmece %s, Python %s (klasördeki: %s) | ana sayfa geldi: %s | kapandı: %s" % (
            n, os.path.getsize(A.paket) // (1024 * 1024), oku, bool(d), d and d["surum"], d and d["calisma"]["python"], d and d["calisma"]["gomulu"],
            bool(d) and ("Sürüm " + d["surum"]) in sayfa, kapandi)
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


@senaryo("B11", "macOS ve Linux açılış dosyaları pakette: '#!/bin/sh' ile başlıyor, satır sonları LF, zip'te çalıştırma izni yazılı, imece.py'yi çağırıyor")
def _():
    if not A.paket:
        return False, "paket verilmedi (--paket)"
    with zipfile.ZipFile(A.paket) as z:
        bulunan = {}
        for i in z.infolist():
            if i.filename in ("imece/Imece-Ac.command", "imece/imece-ac.sh"):
                v = z.read(i)
                bulunan[i.filename.split("/")[-1]] = {
                    "bas": v.startswith(b"#!/bin/sh\n"), "lf": b"\r" not in v, "izin": oct((i.external_attr >> 16) & 0o777),
                    "unix": i.create_system == 3, "cagri": b'exec "$p" imece.py "$@"' in v, "ascii": v.isascii()}
    tamam = len(bulunan) == 2 and all(b["bas"] and b["lf"] and b["izin"] == "0o755" and b["unix"] and b["cagri"] and b["ascii"] for b in bulunan.values())
    return tamam, "%s. Bu dosyalar ÇALIŞTIRILMADI: bu bilgisayarda macOS ya da Linux yok; yalnızca biçimleri denetlendi." % (
        " | ".join("%s: sh başlığı %s, LF %s, izin %s, imece.py çağrısı %s" % (ad, b["bas"], b["lf"], b["izin"], b["cagri"]) for ad, b in sorted(bulunan.items())) or "pakette yok")


g = len([1 for s in SONUC if s["durum"] == "GEÇTİ"])
print("\n%d senaryo: %d geçti, %d kaldı" % (len(SONUC), g, len(SONUC) - g))
if A.json:
    with open(A.json, "w", encoding="utf-8") as f:
        json.dump({"sonuc": SONUC}, f, ensure_ascii=False, indent=1)
sys.exit(0 if g == len(SONUC) else 1)
