# İmece

**İnternet yokken de elinin altında duran Türkçe bilgi arşivi ve afet rehberi.** Açık kaynak, reklamsız, veri toplamaz.

İmece'yi bir kere kurar, istediğin içeriği indirirsin; ondan sonra internet, şebeke ya da elektrik olsun olmasın
bilgisayarında, flash diskinde ya da evdeki küçük bir kutuda çalışır. Aynı Wi-Fi'daki telefonlar da okuyabilir.

> English summary is at the bottom of this page.

## İçinde ne var

| Bölüm | Ne işe yarar |
|---|---|
| **Afet rehberleri** | Deprem, su, ilk yardım, ısınma, iletişim, gıda, yenilebilir bitkiler, halk ilaçları ve adım adım sesli kanama rehberi. Her bilgi bir kaynağa bağlıdır; kaynaklar bölümün altında sayılır. |
| **Kütüphane** | Vikipedi (resimli), Vikisözlük, Vikikitap, Vikikaynak, tıp ve tamir kaynakları, fen deneyleri… Hepsinde tek aramayla, yazıların içinde arama. |
| **Sanat** | Osman Hamdi Bey'den Van Gogh'a kamu malı tablolar; her eserin altında ressamı, tarihi ve kaynağı. |
| **Müzik** | Kamu malı ve açık lisanslı klasik müzik kayıtları, çalma listesiyle. |
| **Oyunlar** | Satranç, sudoku, mangala. İnternet istemez. |
| **Paketler** | Mini (telefon / 16 GB), Standart (64 GB), Tam (256 GB+) hazır seçimler ya da tek tek indirme. İndirme yarıda kalırsa kaldığı yerden sürer; inen her dosyanın sağlaması denetlenir. |
| **Paylaşım** | Kütüphaneyi aynı ağdaki cihazlara aç; kare kodu okutan telefon bağlanır. Başka bir İmece'den internetsiz kitap kopyala. Hepsini bir flash diske kur. |

Arayüz Türkçedir; sağ üstteki **TR | EN** düğmesiyle İngilizceye çevrilir (rehber metinleri Türkçe kalır).

## Nasıl kullanılır

**Windows 10/11:** [Sürümler](../../releases) sayfasından `imece-…-windows.zip` dosyasını indir, klasöre çıkar,
`Imece-Ac` dosyasına çift tıkla. Hiçbir şey kurmak gerekmez.

**Linux, macOS, Raspberry Pi:** Python 3.14 kurulu olmalı. Bu depoyu indir ve çalıştır:

```bash
python3 imece.py
```

Uygulama tarayıcıda açılır. Kapatmak için sağ üstteki "İmece'yi kapat" düğmesine bas.

## Değişmez kurallar

1. Sahte, kaynaksız ya da doğrulanmamış bilgi yok. Sağlık ve güvenlik metni uzman onayı olmadan "kesin" gösterilmez.
2. Tamamen açık kaynak. İçerik ya açık lisanslıdır (Wikimedia, kamu malı, Creative Commons) ya da hak sahibi onu
   İmece'de ücretsiz okunsun diye bağışlamıştır ([ESER-BAGISI.md](ESER-BAGISI.md)). İzinsiz telifli içerik yok.
3. Kod kendi kodumuzdur; başka projelerin yazılımı kullanılmaz (Windows paketindeki resmî Python çalışma ortamı dışında).
4. İnternetsiz çalışır; reklam yok, veri toplama yok.
5. Türkçe öncelikli; İngilizce isteğe bağlı.
6. Hiçbir şey bilmeyen de anlamalı: uyarılar başta, adım adım.
7. Kullanıcı komut satırı ya da klasör karmaşası görmez; her şey uygulamanın içinden yapılır.

## Şu anki durum — dürüstçe

- **Rehberleri henüz bir uzman onaylamadı.** Metinler AFAD, Sağlık Bakanlığı, Dünya Sağlık Örgütü, ERC, NHS, CDC gibi
  kaynaklar okunarak yazıldı ve her bölüm ekranda "KAYNAKLI · UZMAN ONAYI BEKLİYOR" diye görünür. Eğitimin ve sağlık
  görevlisinin yerini tutmaz. Onaylayacak ilk yardım eğitmeni, hekim ve afet uzmanı arıyoruz:
  [belgeler/REHBER-KAYNAK-VE-ONAY.md](belgeler/REHBER-KAYNAK-VE-ONAY.md).
- Yalnızca Windows'ta ve Chrome'da sınandı. macOS ve Linux açılış dosyaları yazıldı ama denenmedi.
- Android ve iOS uygulaması yok; telefon şimdilik aynı ağdaki bir bilgisayara bağlanarak kullanır.
  Yol haritası: [belgeler/PLATFORMLAR.md](belgeler/PLATFORMLAR.md).
- Kitap paketleri [Kiwix](https://kiwix.org) projesinin herkese açık kataloğundan iner (ZIM biçimi açıktır; İmece onu
  kendi okuyucusuyla açar). Resimler Wikimedia Commons'tan, müzik Internet Archive'dan iner.

Ayrıntılı durum ve bilinen sınırlar: [belgeler/PLATFORMLAR.md](belgeler/PLATFORMLAR.md), son test raporu:
[belgeler/TEST-RAPORU-0.19.md](belgeler/TEST-RAPORU-0.19.md), sıradaki işler: [belgeler/YOL-HARITASI.md](belgeler/YOL-HARITASI.md).

## Gönüllü ol

İmece gönüllülerle büyüyor. Üç yoldan katılabilirsin:

| Kimsen | Ne yaparsın | Nereden başlarsın |
|---|---|---|
| **Uzman** (hekim, ilk yardım eğitmeni, afet uzmanı, eczacı, mühendis…) | Kendi alanındaki rehberi okur, düzeltir, onaylarsın | [UZMAN-GONULLU.md](UZMAN-GONULLU.md) |
| **Eser sahibi** (yazar, çizer, müzisyen, kurum) | Faydalı bir eserini İmece'de ücretsiz okunsun diye bağışlarsın | [ESER-BAGISI.md](ESER-BAGISI.md) |
| **Geliştirici / denemeci** | Kod yazar, farklı cihazlarda dener, hata bildirirsin | [CONTRIBUTING.md](CONTRIBUTING.md) |

Bir hatayı, öneriyi ya da katılma isteğini GitHub'da **Issues → New issue** ile bildirebilirsin; hazır formlar var.

## Lisans

- **Kod:** MIT (bkz. [LICENSE](LICENSE)).
- **Rehber metinleri** (`uygulama/index.html` içindeki rehber bölümleri ve `uygulama/rehberler/`): CC BY-SA 4.0.
- **İndirilen içerikler** kendi lisanslarıyla dağıtılır; her paketin lisansı Paketler bölümünde yazar.
- Windows paketindeki `python/` klasörü python.org'un resmî, değiştirilmemiş paketidir; lisansı o klasördedir.

---

## English summary

**İmece** (Turkish for "communal work") is an open-source, offline knowledge archive and disaster-preparedness guide,
Turkish first. Install it once, download the content you want, and it keeps working without internet on a PC, a flash
drive or a small home server; phones on the same Wi-Fi can read it too.

- Sourced emergency guides in Turkish (earthquake, water, first aid, warmth, communication, food) — **sourced but not
  yet reviewed by experts**, and labelled as such in the app.
- Offline library (Wikipedia with images, Wiktionary, Wikibooks, medical and repair references) with full-text search.
- Public-domain art galleries, open-licensed classical music, chess / sudoku / mangala.
- Single-file Python standard-library server with its own ZIM reader; no third-party code, no ads, no tracking.
- Interface in Turkish and English (the guides themselves are Turkish only).

Run: download the Windows zip from Releases and double-click `Imece-Ac`, or `python3 imece.py` (Python 3.14) elsewhere.
Code is MIT; guide texts are CC BY-SA 4.0. Volunteers welcome: experts to review the guides, rights holders to
donate works for in-app reading, developers and testers (see the files above, in Turkish).
