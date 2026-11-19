# İmece'ye katkı

İmece gönüllülerle gelişen, açık kaynak bir projedir. Her katkı değerlidir; bir yazım hatasını bildirmek de buna dahil.

## Katkı yolları

| Ne yapmak istiyorsun | Rehber |
|---|---|
| Bir rehberi uzman olarak okuyup onaylamak | [UZMAN-GONULLU.md](UZMAN-GONULLU.md) |
| Bir eserini İmece'de okunsun diye bağışlamak | [ESER-BAGISI.md](ESER-BAGISI.md) |
| Farklı cihazlarda denemek | Aşağıda, "Deneme" |
| Kod yazmak | Aşağıda, "Kod" |
| Açık lisanslı içerik önermek | Aşağıda, "İçerik önerisi" |

Hata, öneri ya da katılma isteği için GitHub'da **Issues → New issue** bölümündeki hazır formları kullan.

## Değişmez kurallar

Her katkı, [README.md](README.md) içindeki **Değişmez kurallar**a uymalıdır. Özellikle:

1. Sahte, kaynaksız ya da doğrulanmamış bilgi yok. Sağlık ve güvenlik metni uzman onayı olmadan "kesin" gösterilmez.
2. İzinsiz telifli içerik yok.
3. Başka projelerin yazılımı kullanılmaz; `imece.py` yalnızca Python'un kendi kitaplığını kullanır.
4. Reklam yok, veri toplama yok, internetsiz çalışır.
5. Türkçe önceliklidir.
6. Hiçbir şey bilmeyen de anlamalıdır.
7. Kullanıcı komut satırı ya da klasör karmaşası görmez.

Kuralları bozan bir değişiklik kabul edilmez.

## Deneme

En çok ihtiyaç duyulan denemeler [belgeler/YOL-HARITASI.md](belgeler/YOL-HARITASI.md) dosyasında listeli: Windows 10,
gerçek flash disk, telefon, macOS, Linux, Raspberry Pi. Denediğin cihazı, işletim sistemini, tarayıcıyı ve takıldığın
adımı **"Hata bildirimi"** formuyla yaz. Ekran görüntüsü çok yardımcı olur.

## Kod

- `imece.py`: tek dosyalık sunucu. Yalnızca Python 3.14 standart kitaplığını kullanır.
- `uygulama/`: tarayıcıda açılan arayüz (HTML, JavaScript). Rehber metinleri ve kaynakları da buradadır.
- `gelistirme/`: paketleme, Windows için Python gömme, rehber onay denetimi, Raspberry Pi kurulumu ve testler.

Çalıştırmak için:

```bash
python3 imece.py
```

Testler `gelistirme/test/` klasöründedir. Bir değişiklik göndermeden önce ilgili testleri çalıştır, sonuçlarını
değişiklik açıklamasına ekle.

Değişiklik göndermek için depoyu kendi hesabına kopyala (fork), değişikliğini yap ve bir **Pull Request** aç.
Açıklamada neyi neden değiştirdiğini sade bir dille yaz.

## Rehber metinleri

Rehber metinlerinde değişiklik yapacaksan önce
[belgeler/REHBER-KAYNAK-VE-ONAY.md](belgeler/REHBER-KAYNAK-VE-ONAY.md) dosyasını oku. Kısaca:

- Her bilgi birincil ve yetkili bir kaynağa bağlanır (AFAD, Sağlık Bakanlığı, Kızılay, DSÖ, ERC…). Vikipedi, haber
  sitesi ve bloglar kaynak sayılmaz.
- Kaynaktan alıntı yapılmaz; metin kendi cümlelerimizle yazılır.
- Onaylı bir bölümü değiştirmek onayı geçersiz kılar. Değişiklik uzmana yeniden gösterilmelidir.

## İçerik önerisi

Lisansı açıkça belli, açık lisanslı (kamu malı, CC0, CC BY, CC BY-SA) Türkçe kaynakları **"İçerik önerisi"**
olarak bildirebilirsin. Ticari kullanımı (NC) ya da türev eseri (ND) yasaklayan lisanslar kataloğa alınmaz. Böyle bir
eserin sahibi sensen [ESER-BAGISI.md](ESER-BAGISI.md) dosyasına bak.

## Lisans

Katkıda bulunduğun kod MIT, rehber metinleri CC BY-SA 4.0 lisansıyla yayımlanır (bkz. [LICENSE](LICENSE)).
Katkı göndererek bunu kabul etmiş olursun.
