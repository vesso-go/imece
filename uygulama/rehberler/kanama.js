// İmece rehber formatı v1 — karar ağacı.
// Her düğüm: baslik, metin (ekranda), ses (sesli okunan metin; yoksa metin okunur),
// uyarilar [{seviye: "tehlike"|"dikkat"|"not", metin}], adimlar [], secenekler [{etiket, git}],
// sayac {saniye, aralik, ses, bitis} (eller serbest sayaç), son: true (bitiş düğümü),
// kn [kaynak numaraları]: düğümdeki bilgilerin dayandığı kaynaklar (liste: rehber-kaynak.js → bolumler.kanama).
window.REHBER = {
  "id": "kanama",
  "baslik": "Kanama",
  "surum": "2026-11-19",
  "baslangic": "guvenlik",
  "dugumler": {
    "guvenlik": {
      "baslik": "Önce güvenlik",
      "metin": "Yaralıya yaklaşmadan önce çevreye bak.",
      "adimlar": [
        "Yaklaşmak güvenli mi? Trafik, dökülmüş kimyasal madde, saldırgan biri var mı?",
        "Varsa eldiven tak.",
        "112'yi ara ya da yanındaki birine arat. Telefonu hoparlöre al."
      ],
      "uyarilar": [
        {"seviye": "tehlike", "metin": "Ortam güvenli değilse yaklaşma."}
      ],
      "ses": "Önce güvenlik. Yaralıya yaklaşmadan önce çevreye bak. Trafik, dökülmüş kimyasal madde ya da saldırgan biri varsa yaklaşma. Varsa eldiven tak. 112'yi ara ya da yanındaki birine arat, telefonu hoparlöre al.",
      "kn": [1, 2, 5, 6],
      "secenekler": [{"etiket": "Ortam güvenli, devam", "git": "nerede"}, {"etiket": "Güvenli değil", "git": "guvensiz"}]
    },
    "guvensiz": {
      "baslik": "Ortam güvenli değil",
      "metin": "Kendini tehlikeye atma.",
      "adimlar": ["Uzaktan 112'yi ara ya da arat.", "Tehlike geçince bu rehbere geri dön."],
      "uyarilar": [{"seviye": "dikkat", "metin": "Yaralıyı güvenli bir yere taşımayı ancak mümkünse ve senin için güvenliyse dene."}],
      "ses": "Ortam güvenli değil. Kendini tehlikeye atma. Uzaktan 112'yi ara. Yaralıyı güvenli bir yere taşımayı ancak senin için güvenliyse dene. Tehlike geçince rehbere geri dön.",
      "kn": [1, 4],
      "secenekler": [{"etiket": "Tehlike geçti", "git": "nerede"}]
    },
    "nerede": {
      "baslik": "Kanama nerede?",
      "metin": "Kanamanın kaynağını bul.",
      "ses": "Kanama nerede? Kanamanın kaynağını bul ve seç.",
      "kn": [5],
      "secenekler": [
        {"etiket": "Kol ya da bacak", "git": "uzuv_siddet"},
        {"etiket": "Boyun, göğüs, karın, sırt, kasık", "git": "govde"},
        {"etiket": "Burun", "git": "burun"},
        {"etiket": "Yaraya bir cisim saplanmış", "git": "saplanmis"}
      ]
    },
    "uzuv_siddet": {
      "baslik": "Kanama ne kadar?",
      "metin": "Kanamanın şiddetine bak.",
      "adimlar": ["CİDDİ (hayatı tehdit eden): Kan fışkırıyor, hızla akıyor ya da yerde gölleniyor.", "HAFİF: Bunların hiçbiri yok."],
      "ses": "Kanama ne kadar? Kan fışkırıyor, hızla akıyor ya da yerde gölleniyorsa ciddidir. Bunların hiçbiri yoksa hafiftir.",
      "kn": [4],
      "secenekler": [{"etiket": "Ciddi", "git": "bastir"}, {"etiket": "Hafif", "git": "hafif"}]
    },
    "bastir": {
      "baslik": "Bastır",
      "metin": "Yaranın üstüne doğrudan ve sıkıca bastır.",
      "adimlar": [
        "Elinde ne varsa onunla bastır: sargı bezi ya da katlanmış temiz bir bez (örneğin havlu).",
        "Bezi yaranın tam üstüne koy; üstünden elinle sıkıca ve aralıksız bastır.",
        "Yaralı kol ya da bacak sert, düz bir yüzeyde dursun.",
        "Kanama durana ya da yardım gelene kadar baskıyı bırakma."
      ],
      "uyarilar": [
        {"seviye": "tehlike", "metin": "Kol ya da bacaktaki, hayatı tehdit eden kanama baskıyla durmuyorsa bekleme: hemen turnikeye geç."},
        {"seviye": "dikkat", "metin": "Bez kanla dolarsa ne yapılacağında kaynaklar ayrışıyor: İngiltere sağlık hizmeti (NHS) üstüne yeni bir bez koymayı, İngiliz Kızılhaçı ıslanan bezi yenisiyle değiştirmeyi söylüyor. İkisinde de ortak olan: sıkı baskıyı sürdür."}
      ],
      "ses": "Bastır. Sargı bezi ya da katlanmış temiz bir bezi yaranın tam üstüne koy. Üstünden elinle sıkıca ve aralıksız bastır. Yaralı kol ya da bacak sert, düz bir yüzeyde dursun. Kanama durana ya da yardım gelene kadar bırakma. Kol ya da bacaktaki kanama baskıyla durmuyorsa bekleme, turnikeye geç.",
      "kn": [1, 4, 5, 6, 7],
      "secenekler": [{"etiket": "Kanama durdu / yavaşladı", "git": "sar"}, {"etiket": "Bastırmama rağmen durmuyor", "git": "turnike"}]
    },
    "turnike": {
      "baslik": "Turnike",
      "metin": "Yalnızca kol ve bacakta; doğrudan baskıyla durmayan, hayatı tehdit eden kanamada.",
      "adimlar": [
        "Hazır (üretilmiş) turnike varsa onu kullan.",
        "Yaranın 5–7 cm üstüne, eklemin üstüne gelmeyecek biçimde tak.",
        "Kanama yavaşlayıp durana kadar sık. Yaralının canı yanabilir.",
        "Taktığın saati turnikenin üstüne yaz.",
        "Hazır turnike yoksa: en az 5 cm genişliğinde bir bezi sar, yarım düğüm at, üstüne bir çubuk koy, tam düğüm at; çubuğu kanama durana kadar çevir ve sabitle."
      ],
      "uyarilar": [
        {"seviye": "tehlike", "metin": "Turnikeyi taktıktan sonra gevşetme, çıkarma. Bunu yalnızca sağlık görevlisi yapar."},
        {"seviye": "tehlike", "metin": "İp, tel gibi ince malzeme kullanma: dar turnike daha çok ağrı ve doku hasarı yapar, daha az işe yarar."},
        {"seviye": "dikkat", "metin": "Doğaçlama turnike hazır turnike kadar iyi değildir. Kılavuzlar onu ancak hazır turnike yoksa, baskı işe yaramıyorsa ve uygulayan kişi bu konuda eğitim aldıysa öneriyor. Çubuklu yöntemin tarifi Sağlık Bakanlığı'nın 1994 tarihli kitabındandır; güncel kılavuzlar tarif vermiyor."}
      ],
      "ses": "Turnike. Yalnızca kol ve bacakta, baskıyla durmayan kanamada. Hazır turnike varsa onu kullan. Yaranın beş ila yedi santim üstüne, eklemin üstüne gelmeyecek biçimde tak. Kanama durana kadar sık; yaralının canı yanabilir. Taktığın saati turnikenin üstüne yaz. Turnikeyi gevşetme, çıkarma. İp ya da tel kullanma.",
      "kn": [1, 3, 4, 9],
      "secenekler": [{"etiket": "Kanama durdu", "git": "sok"}, {"etiket": "Hâlâ kanıyor", "git": "turnike_iki"}]
    },
    "turnike_iki": {
      "baslik": "Turnike yetmedi",
      "metin": "Daha sık ya da ikinci bir turnike tak.",
      "adimlar": ["Turnikeyi biraz daha sık.", "Yine durmazsa ilk turnikenin yukarısına ikinci bir turnike tak."],
      "uyarilar": [{"seviye": "tehlike", "metin": "İlk turnikeyi gevşetme, çıkarma."}],
      "ses": "Turnike yetmedi. Biraz daha sık. Yine durmazsa ilk turnikenin yukarısına ikinci bir turnike tak. İlkini gevşetme, çıkarma.",
      "kn": [1],
      "secenekler": [{"etiket": "Devam", "git": "sok"}]
    },
    "govde": {
      "baslik": "Gövde, boyun, kasık",
      "metin": "Turnike yalnızca kol ve bacakta işe yarar. Burada bastır.",
      "adimlar": [
        "Yaranın üstüne bez koy; elinle sıkıca ve aralıksız bastır.",
        "Yara sıkıştırma (bezi yaranın içine doldurma) eğitimi aldıysan: kafa derisi, boyun, omuz, kasık ve sırttaki hayatı tehdit eden kanamada uygula.",
        "Kanama durana ya da yardım gelene kadar bırakma."
      ],
      "uyarilar": [
        {"seviye": "tehlike", "metin": "Göğüste açık yara varsa üstünü kapatma, sargı koyma; açık bırak. Yalnızca gerekiyorsa, kanayan yere doğrudan bastır."},
        {"seviye": "dikkat", "metin": "Yaralı nefes almakta zorlanıyorsa en rahat nefes aldığı duruşta kalsın; bu çoğu zaman oturur durumdur."}
      ],
      "ses": "Gövde, boyun ya da kasık. Turnike yalnızca kol ve bacakta işe yarar; burada bastır. Yaranın üstüne bez koy, elinle sıkıca ve aralıksız bastır. Göğüste açık yara varsa üstünü kapatma, açık bırak; yalnızca kanayan yere bastır. Kanama durana ya da yardım gelene kadar bırakma.",
      "kn": [1, 4, 5],
      "secenekler": [{"etiket": "Bastırıyorum, sonraki", "git": "sok"}]
    },
    "burun": {
      "baslik": "Burun kanaması",
      "metin": "Otur, öne eğil, burnunu sık.",
      "adimlar": [
        "Otur; başını hafifçe öne eğ, ağzın açık olsun.",
        "Burnunu, burun deliklerinin hemen üstünden sık.",
        "10–15 dakika bırakmadan sık; ağızdan nefes al.",
        "Durduktan sonra 24 saat burnunu sümkürme, burnunla oynama, dümdüz yatma."
      ],
      "uyarilar": [
        {"seviye": "dikkat", "metin": "15 dakika aralıksız sıkmaya rağmen durmuyorsa, kafaya alınan bir darbeden sonra başladıysa, kan çok fazlaysa ya da kusacak kadar kan yutuyorsan: 112'yi ara ya da acile git."},
        {"seviye": "not", "metin": "Kan sulandırıcı ilaç kullanıyorsan ve kanama durmadıysa sağlık kuruluşuna başvur."}
      ],
      "ses": "Burun kanaması. Otur ve başını hafifçe öne eğ. Burnunu, burun deliklerinin hemen üstünden sık. On beş dakika bırakma, ağızdan nefes al. On beş dakikada durmazsa ya da kafaya alınan bir darbeden sonra başladıysa yardım çağır.",
      "sayac": {"saniye": 900, "aralik": 300, "ses": "{dk} dakika geçti. Sıkmaya devam.", "bitis": "On beş dakika doldu. Kanama durmadıysa yardım çağır."},
      "kn": [4, 8],
      "secenekler": [{"etiket": "Durdu", "git": "bitti"}, {"etiket": "15 dakikada durmadı", "git": "yardim"}]
    },
    "saplanmis": {
      "baslik": "Saplanmış cisim",
      "metin": "Cismi çıkarma.",
      "adimlar": [
        "Cismi olduğu yerde bırak: deliği tıkıyor ve kanı tutuyor olabilir.",
        "Cismin üstüne değil, iki yanına sıkıca bastır.",
        "112'yi ara ya da acile git."
      ],
      "ses": "Saplanmış cisim. Cismi çıkarma; deliği tıkıyor ve kanı tutuyor olabilir. Cismin üstüne değil, iki yanına sıkıca bastır. 112'yi ara.",
      "kn": [6, 7],
      "secenekler": [{"etiket": "Bastırıyorum, sonraki", "git": "sok"}]
    },
    "hafif": {
      "baslik": "Hafif kanama",
      "metin": "Temizle, bastır, ört.",
      "adimlar": [
        "Ellerini yıka; varsa eldiven tak.",
        "Yarayı akan musluk suyuyla ya da şişe suyuyla, içinde görünür kir kalmayana kadar yıka.",
        "Temiz bir bezle kurula; kanıyorsa temiz bir bezle bastır.",
        "Temiz bir sargıyla ya da yara bandıyla ört."
      ],
      "uyarilar": [
        {"seviye": "not", "metin": "Yarayı yıkamak için antiseptik (örneğin iyotlu çözelti) gerekmez; akan musluk suyu yeter."},
        {"seviye": "dikkat", "metin": "Hayvan ya da insan ısırığıyla oluşan yara için en kısa zamanda sağlık kuruluşuna git."}
      ],
      "ses": "Hafif kanama. Ellerini yıka. Yarayı akan suyla, içinde kir kalmayana kadar yıka. Temiz bir bezle kurula ve bastır. Temiz bir sargıyla ya da yara bandıyla ört.",
      "kn": [4, 7],
      "secenekler": [{"etiket": "Tamam", "git": "bitti"}]
    },
    "sar": {
      "baslik": "Sar",
      "metin": "Kanama denetim altına girince baskılı sargı yap.",
      "adimlar": [
        "Bezin üstünden sargıyı sıkıca sar ve sabitle.",
        "Sargının çok sıkı olmadığını anlamak için sargının ötesindeki kan dolaşımını 10 dakikada bir denetle."
      ],
      "uyarilar": [{"seviye": "dikkat", "metin": "Sargıdan yeniden kan gelirse elle doğrudan bastırmaya geri dön."}],
      "ses": "Sar. Bezin üstünden sargıyı sıkıca sar ve sabitle. Sargının çok sıkı olmadığını anlamak için ötesindeki kan dolaşımını on dakikada bir denetle. Yeniden kan gelirse elle bastırmaya geri dön.",
      "kn": [1, 5, 7],
      "secenekler": [{"etiket": "Sardım", "git": "sok"}]
    },
    "sok": {
      "baslik": "Şok kontrolü",
      "metin": "Çok kan kaybeden kişi şoka girebilir. Belirtilere bak.",
      "adimlar": [
        "Belirtiler: çok hızlı ya da çok yavaş nabız; soluk, soğuk ya da nemli deri; baş dönmesi ya da bilinç bulanıklığı.",
        "Sırtüstü yatır.",
        "Üşümesini önle: üstünü kuru battaniye ya da giysiyle ört, soğuk zeminle arasına battaniye gibi bir yalıtım koy.",
        "Yardım gelene kadar yanında kal.",
        "Durumunu izle: kötüleşirse ya da yanıt vermez olursa nefesine bak."
      ],
      "uyarilar": [
        {"seviye": "dikkat", "metin": "Bacaklarını kaldırma. Kılavuzlar bunu yalnızca yaralanma olmayan durumlar için, o da geçici bir önlem olarak anıyor; yaralıyı sırtüstü tut."},
        {"seviye": "not", "metin": "Sağlık Bakanlığı'nın 1994 tarihli kitabı şoktaki kişiye ağızdan hiçbir şey verilmemesini söylüyor. Güncel kılavuzlarda bu konuda bir madde bulamadık."}
      ],
      "ses": "Şok kontrolü. Nabız çok hızlı ya da çok yavaşsa, deri soluk, soğuk ya da nemliyse, baş dönmesi ya da bilinç bulanıklığı varsa şok olabilir. Sırtüstü yatır. Bacaklarını kaldırma. Üstünü ört, altına bir şey ser. Yanından ayrılma, durumunu izle.",
      "kn": [1, 3, 4, 9],
      "secenekler": [{"etiket": "Yanıt vermiyor / normal nefes almıyor", "git": "nefes"}, {"etiket": "Bilinçli, nefes alıyor", "git": "yardim"}]
    },
    "nefes": {
      "baslik": "Yanıt vermiyor, normal nefes almıyor",
      "metin": "Temel yaşam desteğine geç (yetişkin).",
      "adimlar": [
        "112 aranmadıysa hemen ara; telefonu hoparlöre al.",
        "Göğsün ortasına (göğüs kemiğinin alt yarısına) bir elinin topuğunu, onun üstüne öbür elini koy.",
        "Kolların düz; dakikada 100–120 hızla, en az 5, en çok 6 cm derinlikte bas.",
        "Kurtarıcı nefes eğitimi aldıysan 30 bası, 2 nefes. Almadıysan aralıksız bas.",
        "Otomatik şok cihazı (OED) gelirse hemen tak ve söylediklerini yap.",
        "Yardım gelip devralana ya da durmanı söyleyene kadar sürdür."
      ],
      "ses": "Yanıt vermiyor ve normal nefes almıyor. Hemen 112'yi ara, telefonu hoparlöre al. Göğsün ortasına bir elinin topuğunu, üstüne öbür elini koy. Kolların düz, dakikada yüz ila yüz yirmi kez, beş altı santim derinlikte bas. Nefes eğitimi aldıysan otuz bası, iki nefes; almadıysan aralıksız bas. Yardım gelene kadar bırakma.",
      "kn": [1, 2],
      "son": true
    },
    "yardim": {
      "baslik": "Yardım çağır ve bekle",
      "metin": "Sağlık yardımı gerekli.",
      "adimlar": ["112 aranmadıysa ara ya da arat.", "Yardım gelene kadar yaralının yanında kal ve baskıyı sürdür."],
      "ses": "Yardım çağır ve bekle. 112 aranmadıysa ara. Yardım gelene kadar yaralının yanında kal ve baskıyı sürdür.",
      "kn": [4, 6],
      "son": true
    },
    "bitti": {
      "baslik": "Tamam",
      "metin": "Kanama denetim altında.",
      "adimlar": ["Yarada kızarıklık, şişlik, kötü kokulu akıntı, artan ağrı ya da ateş olursa sağlık kuruluşuna git."],
      "ses": "Kanama denetim altında. Yarada kızarıklık, şişlik, kötü kokulu akıntı, artan ağrı ya da ateş olursa sağlık kuruluşuna git.",
      "kn": [4],
      "son": true
    }
  }
};
