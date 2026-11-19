#!/bin/sh
# Imece'yi bir Raspberry Pi'ye (ya da baska bir Linux kutusuna) servis olarak kurar.
# DENENMEDI: bu betik bir Pi uzerinde hic calistirilmadi. Calistirmadan once oku.
# Kullanim (Imece klasorunun icinden):  sudo sh gelistirme/pi/kur.sh
set -e
if [ "$(id -u)" != "0" ]; then echo "Bu betik yonetici olarak calistirilmali: sudo sh gelistirme/pi/kur.sh"; exit 1; fi
if [ ! -f imece.py ]; then echo "Bu betigi Imece klasorunun icinden calistir (imece.py burada olmali)."; exit 1; fi
if ! command -v python3 >/dev/null 2>&1; then echo "python3 bulunamadi. Once Python 3.14 kur."; exit 1; fi
python3 -c "import sys; print('Python', sys.version.split()[0])"
id imece >/dev/null 2>&1 || useradd --system --home /opt/imece --shell /usr/sbin/nologin imece
mkdir -p /opt/imece
cp -r imece.py uygulama belgeler /opt/imece/
if [ -d veri ]; then cp -r veri /opt/imece/; else mkdir -p /opt/imece/veri; fi
chown -R imece:imece /opt/imece
cp gelistirme/pi/imece.service /etc/systemd/system/imece.service
systemctl daemon-reload
systemctl enable --now imece
echo "Kuruldu. Durum: systemctl status imece"
echo "Ayni agdaki bir cihazin tarayicisina bu kutunun adresini yaz (ornek: http://<kutunun-ip-adresi>:8642)."
