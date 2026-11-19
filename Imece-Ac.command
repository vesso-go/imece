#!/bin/sh
# Imece'yi acar (macOS: bu dosyaya cift tikla; Linux: imece-ac.sh).
# Bilgisayarda Python 3.14 kurulu olmalidir. Imece tarayicida acilir; kapatmak icin
# uygulamadaki "Imece'yi kapat" dugmesine bas, sonra bu pencereyi kapat.
cd "$(dirname "$0")" || exit 1
for p in python3.14 python3; do
  if command -v "$p" >/dev/null 2>&1; then
    exec "$p" imece.py "$@"
  fi
done
echo
echo "  IMECE ACILAMADI"
echo
echo "  Bu bilgisayarda Python bulunamadi. Imece'nin calismasi icin Python 3.14 gerekir."
echo "  Bir kere, internet varken: https://www.python.org/downloads/ adresinden Python 3.14'u kur,"
echo "  sonra bu dosyayi yeniden ac."
echo
printf "  Kapatmak icin Enter'a bas. "
read _bekle
exit 1
