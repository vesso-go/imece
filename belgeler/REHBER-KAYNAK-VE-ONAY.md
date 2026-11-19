# Rehberlerde kaynak ve uzman onayı nasıl işler

Kural 1: "Sahte, kaynaksız ya da doğrulanmamış bilgi yok. Sağlık/güvenlik metni uzman onayı olmadan 'kesin'
gösterilmez." Bu belge, o kuralın uygulamada nasıl tutulduğunu anlatır.

## Bir rehber bölümünün üç durumu
| Durum | Ekranda | Ne demek |
|---|---|---|
| Taslak | TASLAK · KAYNAK VE UZMAN ONAYI BEKLİYOR | Kaynağı gösterilmemiş metin. Olabildiğince az kalmalı. |
| Kaynaklı | KAYNAKLI · UZMAN ONAYI BEKLİYOR | Her kutu en az bir kaynağa bağlanmış; kaynaklar bölümün altında sayılı. Uzman bakmamış. |
| Onaylı | UZMAN ONAYLI + kimin, ne zaman | Bir uzman, metnin **o günkü hâlini** okuyup onaylamış. |

"Kaynaklı" olmak "doğru" demek değildir: metni kaynaklara bakarak biz yazdık; yanlış anlamış ya da eksik bırakmış
olabiliriz. Bu yüzden kaynaklı metin de ekranda "tek başına güvenme" uyarısıyla durur.

## Dosyalar
- `uygulama/index.html`: rehber metinleri. Her bölümün içeriği `<!--rehber:AD-->` … `<!--/rehber:AD-->` işaretleri
  arasındadır. Bir kutunun dayandığı kaynaklar `<span data-kn="1,3"></span>` ile belirtilir.
- `uygulama/rehberler/*.js`: sesli karar ağaçları (şimdilik yalnızca kanama). Her düğümün dayandığı kaynaklar
  `"kn": [1, 4]` alanıyla belirtilir; ekranda adımın altında "Kaynak: [1] [4]" diye görünür.
- `uygulama/rehber-kaynak.js`: her bölümün durumu, son gözden geçirme tarihi, kaynak listesi ve varsa onay kaydı.
- `gelistirme/rehber_onay.py`: denetim aracı.

## Kaynak eklerken
1. Kaynak birincil ve yetkili olmalı: resmî kurumlar (AFAD, Sağlık Bakanlığı, Kızılay), uluslararası kuruluşlar (DSÖ,
   IFRC, UNICEF), meslek kılavuzları (ERC, AHA), kamu sağlık kurumları (CDC, NHS). Vikipedi, haber siteleri, bloglar ve
   ticari siteler kaynak sayılmaz.
2. Kaynaktan alıntı yapılmaz; metin kendi cümlelerimizle yazılır (kural 2: telifli metin izinsiz alınmaz).
3. Her kaynak için kurum, belge adı, varsa yılı, adresi ve erişim tarihi yazılır.
4. Sayılar (doz, süre, sıcaklık) kaynaktaki hâliyle yazılır. Kaynaklar birbirini tutmuyorsa metin bunu söyler ya da
   daha temkinli olanı verir.
5. Kaynağı bulunamayan cümle metinden çıkarılır. "Herkes bilir" kaynak değildir.

## Onay nasıl kaydedilir
1. Uzman, bölümün **kaynaklı** hâlini okur (ekrandan ya da çıktısından) ve düzeltmelerini bildirir.
2. Düzeltmeler işlenir. Sonra `python gelistirme/rehber_onay.py <imece klasörü> ozet` çalıştırılır; her bölümün özeti
   (64 harflik bir dizi) çıkar.
3. `rehber-kaynak.js` içinde o bölüme onay kaydı eklenir:
   `"onay": {"ad": "…", "unvan": "…", "kurum": "…", "tarih": "YYYY-AA-GG", "ozet": "<o bölümün özeti>"}`
4. `python gelistirme/rehber_onay.py <imece klasörü> denetle` "Sorun yok" demelidir.

Onay metne bağlıdır: onaydan sonra bölümde tek harf değişirse özet değişir, uygulama o bölümü yeniden
"onay bekliyor" gösterir ve "önceki onay geçersiz" diye yazar. Onayı korumak için değişiklik uzmana yeniden gösterilir.

## 0.16'daki durum (19.11.2026)
On bölümün onu da "kaynaklı", hiçbiri "onaylı" değil. Metinler, kaynak sayfaları açılıp okunarak bir yapay zekâ
oturumunda yazıldı; bir uzman okumadı. Türkiye'ye özgü güncel ilk yardım kaynakları (Sağlık Bakanlığı'nın güncel İlk
Yardım Eğitim Kitabı, Kızılay) o oturumda açılamadı; onaylayacak uzmandan özellikle bunlarla karşılaştırması istenmeli.
Her bölümün `not` alanı, önceki sürüme göre neyin neden çıkarıldığını ya da düzeltildiğini yazar.

## Bu düzenin çözmediği ve karar bekleyen şeyler
- **Onaylayan kişinin gerçekten o kişi ve gerçekten uzman olduğunu uygulama bilemez.** Kayıt, projeyi yürütenlerin
  beyanıdır. Kimin onaylayacağı, uzmanlığının nasıl belgeleneceği ve onayın nerede saklanacağı (imzalı bir yazı, e-posta)
  proje sahibinin kararıdır. Bu karar verilmeden hiçbir bölüme onay kaydı eklenmemelidir.
- Onay kaydı dosyada düz yazıdır; dosyayı değiştiren biri sahte bir onay ekleyebilir. Bunun çözümü paketlerin
  imzalanmasıdır (yol haritasında ayrı bir iş).
- Kaynakların kendisi zamanla değişir (kılavuzlar güncellenir). Her bölümde "son gözden geçirme" tarihi durur; bir yıldan
  eski olanlar yeniden gözden geçirilmelidir. Uygulama, tarihin üstünden bir yıldan çok geçince bölümün başına
  "GÖZDEN GEÇİRME GECİKTİ" yazar (cihazın saatine bakar; saat yanlışsa uyarı da yanlış olabilir). Metni gizlemez.
