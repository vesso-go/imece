# İmece — yol haritası

0.19 ile Windows'ta çalışan bir sürüm var. Aşağıdakiler sıradaki işlerdir; her birinin nasıl yapılacağı yazılı.
Katkı vermek istediğin bir madde varsa [CONTRIBUTING.md](../CONTRIBUTING.md) dosyasına bak.

## 1. Gerçek cihazlarda deneme (gönüllüler; her biri yarım saat)
- Hiç İmece görmemiş bir Windows 10 ve bir Windows 11 bilgisayarda: zip'i indir, çıkar, çift tıkla. Çıkan güvenlik
  uyarılarını ve takıldığın yeri not et.
- Gerçek bir flash diske "Flash diske kur", sonra başka bir bilgisayarda aç.
- Telefonla: Ayarlar → paylaşımı aç → kare kodu okut. Windows'un "erişime izin ver" sorusuna "izin ver" de.
- İnterneti kapatıp her bölümü gez.
- macOS'ta `Imece-Ac.command`, Linux'ta `imece-ac.sh` (ikisi de hiç çalıştırılmadı).
Bulduğun her sorunu GitHub'da "Issue" olarak yaz.

## 2. Rehberlerin uzman onayı (bir insan uzman gerekir)
1. İlk yardım eğitmeni / acil hekimi (ilk yardım, kanama), afet uzmanı (deprem, su, gıda), botanikçi ya da eczacı (bitkiler) bul.
2. İlgili bölümü uygulamadan okusun; düzeltmelerini bildirsin. Özellikle Sağlık Bakanlığı'nın güncel ilk yardım
   kitabıyla karşılaştırsın (o kaynak açılamadı).
3. Düzeltmeler işlenir; `belgeler/REHBER-KAYNAK-VE-ONAY.md` içindeki adımlarla onay kaydı eklenir.

## 3. Raspberry Pi kutusu (elde bir Pi gerekir) — `belgeler/PLATFORMLAR.md`
1. `gelistirme/pi/kur.sh` betiğini dene, çıkan hataları düzelt.
2. Kendi Wi-Fi ağını yaymayı kur.
3. Ekransız kutu için parolayla korunan yönetim girişini yaz (indirme ve ayarlar için).
4. Açılış süresini, dizin kurma süresini, aynı anda kaç telefonu kaldırdığını ölç.

## 4. Android (Android geliştirme araçları gerekir) — `belgeler/PLATFORMLAR.md`
1. Karar: çekirdeği Kotlin ile yeniden yazmak mı, Python'u uygulamaya gömmek mi (ikincisi kural 3 için onay ister).
2. Arayüz (`uygulama/`) olduğu gibi bir WebView içinde gösterilir.
3. Play Store için: geliştirici hesabı, imza, gizlilik politikası, içerik beyanı; `TANITIM.md` içindeki mağaza taslağı.

## 5. Kiwix'te olup bizde eksik kalanlar
- Çevrimdışı harita gösterimi (bugün yalnızca ham veri iniyor).
- Video ve büyük ses dosyalarının akıcı oynatılması (denenmedi; büyük dosyada zorlanması beklenir).
- Tarayıcı eklentisi, Android ve iOS uygulaması.
- Paket güncellemesi bildirimi ("bu kitabın yenisi çıktı").
- Kitap içi yer imlerinin dışa aktarılması.

## 6. İçerik
- Türk müziği: lisansı açık kayıt bulunamadı. Hak sahibinden yazılı izin ya da kamu malı eserlerin kendi kaydımız gerekir.
- İndirilebilir oyun paketleri: açık lisanslı, tarayıcıda çalışan oyunlar; her birinin lisansı denetlenmeli.
- "zimgit" el kitabı derlemelerinin lisansları paket paket okunmalı (ticari dağıtımdan önce).
- Kalan 10 sanat galerisinin indirilip gözden geçirilmesi (yanlış kategoriye düşmüş resim var mı).

## 7. Sonraya kalan büyük işler
- Kendi içerik paketlerimiz ve paket imzası (`PLATFORMLAR.md`).
- Gerçek radyo dinleme (USB alıcı gerekir).
- Logo ve tasarım dili; elle şarj olan cihaz.
- İngilizce çevirinin ana dili İngilizce olan birine okutulması.
