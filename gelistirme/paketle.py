"""İmece klasörünü zip'ler. Dosya adları UTF-8 işaretiyle yazılır (Windows'ta 'BENİ OKU.txt' bozulmasın).

Kullanım: python paketle.py <imece klasörünün üstü> <çıktı.zip> [--python]
  --python : klasördeki hazır Python'u (python/) da koyar  -> Windows paketi, kurulum gerektirmez
  yoksa    : yalnızca İmece'nin kendi dosyaları            -> kaynak paketi (Linux, macOS, geliştirici)
"""
import os, sys, zipfile

kok, cikti = sys.argv[1], sys.argv[2]
pythonlu = "--python" in sys.argv[3:]
haric_klasor = {"veri", "__pycache__"} | (set() if pythonlu else {"python"})
haric_dosya = {"ayarlar.json"}
if pythonlu and not os.path.exists(os.path.join(kok, "imece", "python", "pythonw.exe")):
    sys.exit("DURDU: python/ klasörü yok. Önce: python gelistirme/python_gom.py <imece klasörü>")
n = 0
with zipfile.ZipFile(cikti, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for dizin, altlar, dosyalar in os.walk(os.path.join(kok, "imece")):
        altlar[:] = sorted(a for a in altlar if a not in haric_klasor)
        for d in sorted(dosyalar):
            if d in haric_dosya or d.endswith((".pyc", ".yarim", ".log")):
                continue
            tam = os.path.join(dizin, d)
            ad = os.path.relpath(tam, kok).replace(os.sep, "/")
            if d.endswith((".command", ".sh")):
                # macOS/Linux açılış dosyaları: çalıştırma izni zip'e yazılır (Windows'ta dosyanın böyle bir izni
                # olmadığı için elle veriliyor), satır sonları LF olmalı.
                with open(tam, "rb") as f:
                    icerik = f.read()
                if b"\r" in icerik or not icerik.startswith(b"#!/bin/sh\n"):
                    sys.exit("DURDU: %s satır sonları LF olmalı ve '#!/bin/sh' ile başlamalı" % d)
                zi = zipfile.ZipInfo.from_file(tam, ad)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.create_system = 3  # Unix: açan program izinleri buradan okur
                zi.external_attr = 0o100755 << 16
                z.writestr(zi, icerik, compresslevel=9)
            else:
                z.write(tam, ad)
            n += 1
with zipfile.ZipFile(cikti) as z:
    assert z.testzip() is None
    print("%s: %d dosya, %d bayt" % (os.path.basename(cikti), n, os.path.getsize(cikti)))
    py = [i for i in z.infolist() if i.filename.startswith("imece/python/")]
    for i in z.infolist():
        if i in py:
            continue
        print("  %7d  %s%s" % (i.file_size, i.filename, "" if i.filename.isascii() or i.flag_bits & 0x800 else "  (UTF-8 işareti YOK)"))
    if py:
        print("  %7d  imece/python/  (%d dosya: python.org'un resmi paketi, değiştirilmemiş)" % (sum(i.file_size for i in py), len(py)))
