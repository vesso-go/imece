"""Büyük bir kitabın "dosyadan ekle" ile kopyalanması sırasında sunucunun bellek kullanımını ölçer (Windows).
Ayrı, geçici bir İmece kopyasında çalışır; asıl kütüphaneye dokunmaz.
Kullanım: python buyuk_ekle.py <imece klasörü> <büyük .zim dosyası> [--port 8670]"""
import ctypes, http.client, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.parse
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
klasor, kaynak = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8670


class Sayac(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("a", ctypes.c_size_t), ("b", ctypes.c_size_t), ("c", ctypes.c_size_t),
                ("d", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


k32 = ctypes.WinDLL("kernel32")
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
k32.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Sayac), wintypes.DWORD)


def bellek(h):
    s = Sayac()
    s.cb = ctypes.sizeof(s)
    k32.K32GetProcessMemoryInfo(h, ctypes.byref(s), s.cb)
    return s.WorkingSetSize / 2 ** 20


def js(yol, govde=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.request("POST" if govde is not None else "GET", yol, body=json.dumps(govde) if govde is not None else None,
              headers={"Content-Type": "application/json"} if govde is not None else {})
    r = c.getresponse()
    return r.status, json.loads(r.read().decode("utf-8"))


kok = tempfile.mkdtemp(prefix="imece-buyuk-")
shutil.copy(os.path.join(klasor, "imece.py"), kok)
shutil.copytree(os.path.join(klasor, "uygulama"), os.path.join(kok, "uygulama"))
p = subprocess.Popen([sys.executable, os.path.join(kok, "imece.py"), "--port", str(port), "--tarayici-acma"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(80):
        try:
            js("/api/durum")
            break
        except Exception:
            time.sleep(0.25)
    h = k32.OpenProcess(0x1000 | 0x0010, False, p.pid)
    bos = bellek(h)
    boy = os.path.getsize(kaynak)
    olcum, bitti = [], threading.Event()

    def izle():
        while not bitti.is_set():
            olcum.append(bellek(h))
            time.sleep(0.1)
    threading.Thread(target=izle, daemon=True).start()
    t0 = time.time()
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=3600)
    with open(kaynak, "rb") as f:
        c.request("POST", "/api/kitap-ekle?ad=" + urllib.parse.quote(os.path.basename(kaynak)), body=f,
                  headers={"Content-Length": str(boy), "Content-Type": "application/octet-stream"})
        r = c.getresponse()
        yanit = json.loads(r.read().decode("utf-8"))
    sure = time.time() - t0
    bitti.set()
    hedef = os.path.join(kok, "veri", "zim", os.path.basename(kaynak))
    print("kitap: %s, %d MB" % (os.path.basename(kaynak), boy >> 20))
    print("yanıt: %s %s" % (r.status, yanit))
    print("süre: %.1f sn (%.0f MB/sn)" % (sure, (boy >> 20) / sure))
    print("sunucu belleği: eklemeden önce %.0f MB, kopyalama sırasında en çok %.0f MB (%d ölçüm)" % (bos, max(olcum), len(olcum)))
    print("kopya boyutu özgünle aynı: %s" % (os.path.exists(hedef) and os.path.getsize(hedef) == boy))
    kod, s = js("/api/kitap-sil", {"k": yanit.get("id", "")})
    print("silme: %s %s; dosya gitti: %s" % (kod, s, not os.path.exists(hedef)))
finally:
    try:
        js("/api/kapat", {})
        p.wait(20)
    except Exception:
        p.kill()
    shutil.rmtree(kok, ignore_errors=True)
