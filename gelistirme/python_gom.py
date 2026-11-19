"""İmece klasörüne hazır Python'u koyar: python.org'un resmi "embeddable" paketini indirir,
SHA-256 özetini aşağıdaki sabit değerle karşılaştırır ve hiçbir dosyasını değiştirmeden
<imece klasörü>/python içine açar. Paket böylece Python kurulu olmayan Windows'ta da açılır.

Kullanım: python python_gom.py <imece klasörü> [indirilmiş zip]

Sürüm yükseltirken: SURUM ve OZET birlikte değişir. Özet, zip indirildikten sonra
içindeki bütün .exe/.dll/.pyd dosyalarının dijital imzası (Python Software Foundation)
doğrulanarak sabitlenmelidir; test: gelistirme/test/acilis.py B1.
"""
import hashlib, io, os, shutil, sys, urllib.request, zipfile

SURUM = "3.14.6"
MIMARI = "amd64"  # 64 bit Windows 10/11
OZET = "df901e84a896ff1ee720ad03377e0c8d8c2244fda79808aeeaff6316df1cb75c"
ADRES = "https://www.python.org/ftp/python/%s/python-%s-embed-%s.zip" % (SURUM, SURUM, MIMARI)


def main():
    hedef = os.path.join(sys.argv[1], "python")
    if len(sys.argv) > 2:
        with open(sys.argv[2], "rb") as f:
            veri = f.read()
    else:
        print("indiriliyor:", ADRES)
        with urllib.request.urlopen(urllib.request.Request(ADRES, headers={"User-Agent": "Mozilla/5.0"}), timeout=120) as r:
            veri = r.read()
    ozet = hashlib.sha256(veri).hexdigest()
    if ozet != OZET:
        sys.exit("DURDU: özet tutmuyor.\n  beklenen %s\n  gelen    %s" % (OZET, ozet))
    if os.path.isdir(hedef):
        shutil.rmtree(hedef)
    with zipfile.ZipFile(io.BytesIO(veri)) as z:
        z.extractall(hedef)
        n = len(z.namelist())
    print("tamam: Python %s (%s), %d dosya, özet doğrulandı -> %s" % (SURUM, MIMARI, n, hedef))


if __name__ == "__main__":
    main()
