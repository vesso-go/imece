# İmece — öbür platformlar ve büyük işler: ne yapıldı, ne kaldı, nasıl yapılır

Bu belge 19.11.2026'da, 0.19 sürümüyle yazıldı. "Yapıldı" denenler bu depoda duruyor; "denenmedi" denenler yazıldı ama
o cihazda hiç çalıştırılmadı. Buradaki hiçbir adım uydurma bir ölçüye dayanmaz: ölçülmeyen yerde "ölçülmeli" yazar.

## Bugünkü durum

| Nerede | Durum |
|---|---|
| Windows 10/11 | Çalışıyor, sınandı. Kurulum gerekmez. |
| Flash disk | "Flash diske kur" çalışıyor (geçici klasöre denendi; gerçek flash diske denenmedi). |
| Aynı ağdaki telefon / tablet | Çalışıyor: bilgisayardaki İmece paylaşıma açılır, telefon tarayıcıdan bağlanır. Gerçek telefonla denenmedi. |
| macOS, Linux | `Imece-Ac.command` ve `imece-ac.sh` yazıldı. **Denenmedi.** |
| Raspberry Pi | Kurulum betiği ve servis dosyası yazıldı (`gelistirme/pi/`). **Denenmedi.** |
| Android, iOS | Uygulama yok. |

## Raspberry Pi kutusu

Hedef: fişe takınca kendi kendine açılan, kendi Wi-Fi ağını yayan, ekransız bir kutu. Telefonla ağa bağlanan herkes
kütüphaneyi okur. (Kiwix Hotspot, Internet-in-a-Box, Prepper Disk ve RACHEL'ın yaptığı budur.)

**Depoda hazır olan (denenmedi):**
- `gelistirme/pi/kur.sh`: İmece'yi `/opt/imece` içine kopyalar, `imece` adlı bir kullanıcı açar, servisi kurar.
- `gelistirme/pi/imece.service`: açılışta `python3 imece.py --ag --tarayici-acma` çalıştırır, çökerse yeniden başlatır.

**Elinde bir Pi olunca sırayla yapılacaklar:**
1. Raspberry Pi OS (64 bit, masaüstüsüz) kur. `python3 --version` 3.14 mü bak; değilse zstd desteği için Python 3.14
   gerekir (İmece bunu Ayarlar → Hakkında'da söyler). Tam metin arama için Python'daki SQLite'ta FTS5 olmalı;
   yoksa arama yalnızca madde adlarına bakar ve arayüz bunu yazar.
2. `sudo bash gelistirme/pi/kur.sh` çalıştır; `systemctl status imece` ile bak.
3. Kendi Wi-Fi ağını yayması için işletim sisteminin kendi aracı yeter (başka yazılım gerekmez):
   `sudo nmcli device wifi hotspot ssid Imece password <parola>` ve açılışta kendiliğinden açılması için
   `sudo nmcli connection modify Hotspot connection.autoconnect yes`. Bu komutların kullandığın işletim sistemi
   sürümünde aynen çalıştığını doğrula.
4. **Ölç ve yaz:** açılış süresi; 8,5 GB'lık Vikipedi için tam metin dizininin kurulma süresi (bilgisayarda 1,2 GB için
   13 dakikaydı; Pi'de çok daha uzun sürebilir); aynı anda kaç telefonun rahat okuduğu; güç tüketimi.
5. **Eksik olan ve yazılması gereken:** ekransız kutuda paket indirmek. Şu an indirme, silme ve ayarlar yalnızca
   İmece'nin çalıştığı cihazın kendi ekranından yapılabiliyor (güvenlik için). Kutuda bunun için **parolayla korunan bir
   yönetim girişi** gerekir: parola belirleme, oturum, yanlış denemede bekletme. Bu yapılana kadar kutuya içerik, bir
   bilgisayarda hazırlanmış flash diskten "Kitapların durduğu yer" ile ya da ekran-klavye takılarak konur.

## Elle şarj olan cihaz (senin tasarladığın)

Pi kutusuyla aynı yazılım çalışır; fark güçtedir. Tasarlamadan önce ölçülmesi gerekenler: seçilen işlemci kartının boşta
ve yük altında çektiği güç; ekranın çektiği güç; çevirme kolunun dakikada ürettiği enerji. Bu üç sayı olmadan "kaç
dakika çevirince kaç dakika okunur" söylenemez. Yazılım tarafında yardımcı olacak şeyler: tam metin dizinlerini
önceden, fişteyken kurmak (en çok güç isteyen iş budur); arayüzün koyu / gece teması; Wi-Fi yayınını istenince açmak.

## Android

Play Store yalnızca Android uygulaması kabul eder; İmece'nin bugünkü paketleri oraya yüklenemez.
İmece'nin arayüzü zaten bir web sayfası olduğu için uygulama iki parçadan oluşur: arayüzü gösteren bir pencere
(Android'in kendi WebView'u) ve kitapları okuyup sunan çekirdek. İki yol var:

| Yol | Ne demek | Artısı | Eksisi |
|---|---|---|---|
| **A. Çekirdeği Android'in diliyle (Kotlin) yeniden yazmak** | ZIM okuyucu, arama, indirme baştan yazılır; arayüz aynen kullanılır | Hepsi kendi kodumuz (kural 3); küçük ve hızlı uygulama | En çok iş: `imece.py` yaklaşık 2.700 satır; iki ayrı çekirdeğin bakımı |
| **B. Python'u uygulamanın içine gömmek** | `imece.py` aynen çalışır; Python'u Android'e taşıyan hazır bir araç kullanılır | Çok daha az iş; tek çekirdek | O araç başka bir projenin yazılımıdır: **kural 3 için senin onayın gerekir** (Windows'ta resmî Python'u gömmeye onay vermiştin; bu ondan bir adım ötesi) |

**Play Store için ayrıca gerekenler** (başvururken Google'ın kendi sayfasından doğrula; koşullar değişir):
geliştirici hesabı; uygulamanın imzalanması; gizlilik politikası sayfası (İmece veri toplamadığı için kısa olur);
içerik derecelendirme formu; mağaza görselleri; sağlık bilgisi içeren uygulamalar için istenen beyan. Rehberler uzman
onaylı olmadığı için mağaza metninde "tıbbi tavsiye değildir" açıkça yazmalı (`belgeler/TANITIM.md` içindeki taslakta var).

**Bugün telefonda kullanmak için:** bilgisayarda Ayarlar → "Aynı ağdaki cihazlarla paylaş". Play Store'a girmeden
Android'de bağımsız çalışması için yukarıdaki iki yoldan biri şart.

## iOS

Apple, uygulamanın bir Mac'te Xcode ile derlenmesini ve yıllık ücretli geliştirici hesabını ister. Çekirdeğin Swift ile
yeniden yazılması gerekir (A yolunun iOS karşılığı). Android bitmeden başlamak anlamlı değil.

## Radyo: rehber ve gerçek dinleme

- **Rehber:** İletişim bölümünde kaynaklı olarak duruyor (kısa mesaj, pilli radyo, TRT'nin frekans sayfası, kısa dalga,
  PMR446). Tek tek frekans tablosu bilerek konmadı: frekanslar değişir ve uydurma tek bir sayı kural 1'i bozar.
  Konacaksa her satırın kaynağı ve tarihi yazılmalı.
- **Gerçek dinleme:** telefon ve bilgisayar, radyo dalgasını kendi başına alamaz; tarayıcı da telefondaki FM alıcısına
  erişemez. İnternet radyosu ise internet ister. Gerçek dinleme için cihaza takılan bir **USB radyo alıcısı (SDR)**
  gerekir. Bu en doğal olarak Pi kutusunda olur: alıcı kutuya takılır, kutu sesi ağdaki telefonlara verir.
  Engeller: (1) donanım — elde bir alıcı olmalı; (2) alıcıyı çalıştıran sürücü başka bir projenin yazılımıdır, yani
  kural 3 için karar gerekir; sürücüyü sıfırdan yazmak büyük bir iştir; (3) sinyali sese çevirme (FM/AM çözme) kısmı
  kendi kodumuzla yazılabilir. Elinde alıcı olmadan bu iş denenemez; o yüzden başlanmadı.

## "Kendi paketleme hattı" ve "imza" ne demek

- **Bugün:** kitap dosyalarını (Vikipedi vb.) Kiwix projesi hazırlıyor; İmece onların herkese açık kataloğundan indiriyor.
  Resimler Wikimedia Commons'tan, müzik Internet Archive'dan doğrudan iniyor. Yani içerik için başkalarının sunucularına
  bağlıyız; biri kapanırsa ya da adres değiştirirse o içerik inmez.
- **Kendi paketleme hattı:** içerik paketlerini bizim hazırlayıp bizim yayımlamamız. Örnek: Türkçe açık ders kitaplarını,
  AFAD'ın yayımlamasına izin verdiği belgeleri, Türk müziği kayıtlarını toplayıp tek dosya yapmak ve bir adreste (örneğin
  GitHub Releases) tutmak. Bunun için karar gereken tek şey **hangi içeriklerin** ekleneceği; kural açık: yalnızca
  kamu malı ya da açık lisanslı olanlar, lisansı her dosyanın yanında yazılı. 0.19'daki sanat galerileri bu işin ilk
  adımıdır: İmece Commons'tan yalnızca "kamu malı" işaretli resimleri alır ve künyesini kaydeder.
- **İmza:** indirilen bir paketin gerçekten İmece'den geldiğini, yolda değiştirilmediğini kanıtlayan bir mühür. Mühür bir
  gizli anahtarla basılır; o anahtarı projenin sahibi (sen) saklar ve kimseyle paylaşmaz. Kendi paketlerimiz olmadan
  imzalanacak bir şey yoktur; o yüzden paketleme hattından sonra gelir. Bugün İmece inen dosyanın **bozuk olup
  olmadığını** denetliyor ama **kimden geldiğini** denetleyemiyor.

## İndirilebilir oyunlar

0.19'daki üç oyun (satranç, sudoku, mangala) uygulamanın içinde gelir. "İnternetten indirilen oyun paketleri" ayrı bir
iştir: açık lisanslı, tarayıcıda çalışan oyunların paket olarak indirilip Oyunlar bölümünde açılması. Yapılabilir;
dikkat edilecek iki şey var: her oyunun lisansının açık olması ve başka projelerin oyunlarının güvenli bir çerçevede
(kitap sayfaları gibi yalıtılmış) çalıştırılması. Başlanmadı.

## Esinlenilen dört üründe olup İmece'de olmayanlar

Karşılaştırmanın tamamı ve kaynakları `belgeler/TANITIM.md` içinde. Eksikler:

| Onlarda var | İmece'de durum |
|---|---|
| Kendi Wi-Fi ağını yayan hazır kutu | Yazılım hazır (ağ paylaşımı var); kutu kurulumu yukarıda, denenmedi |
| Ekransız kutu için yönetim paneli | Yok (parolalı yönetim girişi yazılmalı) |
| Çevrimdışı harita | Yalnızca ham harita verisi iniyor; haritayı gösteren ekran yok (büyük iş) |
| Khan Academy / Kolibri dersleri, TED videoları | Yok. TED ve iFixit, ticari kullanımı yasaklayan lisansları yüzünden 0.19'da çıkarıldı |
| Project Gutenberg kitapları | Katalogdan tek tek indirilebiliyor; hazır seçimlerde yalnızca tarım kitapları var |
| Android ve iOS uygulaması, tarayıcı eklentisi | Yok |
| Kendi içeriğini yükleme | Kısmen: hazır bir kitap dosyası (.zim) eklenebiliyor |
| Kullanım istatistiği | Yok ve olmayacak (kural 4: veri toplama yok) |
| Yapay zekâ araması | Yok (başka projelerin modelleri gerekir: kural 3) |
