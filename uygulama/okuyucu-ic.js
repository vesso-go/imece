// İmece okuyucu betiği — her kitap sayfasının içine sunucu tarafından eklenir.
// Kitap sayfaları tarayıcıda yalıtılmış çalışır (İmece'nin arayüzüne ve yönetim uçlarına
// dokunamaz). Bu betik, arayüzle sayfa arasındaki tek köprüdür ve sadece şunları yapar:
//   sayfa → arayüz : hangi madde açıldı (yer imi, son okunanlar, başlık), internete giden bağlantıya basıldı,
//                    sayfanın bölüm başlıkları (içindekiler), sayfada bulunanların sayısı, okunacak paragraflar
//   arayüz → sayfa : yazı boyutu, okuma gece modu, geri git, sayfada bul, bölüme git, okunan paragrafı işaretle
(function () {
  if (window.__imece) return;
  window.__imece = 1;
  var ust = window.parent !== window ? window.parent : null;
  function gonder(m) { if (ust) { m.imece = 1; try { ust.postMessage(m, '*'); } catch (e) {} } }

  var stil = document.createElement('style');
  stil.id = 'imece-stil';
  (document.head || document.documentElement).appendChild(stil);
  var sabit = document.createElement('style');
  sabit.textContent = 'mark.imece-bul{background:#ffe066;color:#000;padding:0;border-radius:2px}'
    + 'mark.imece-bul.imece-simdi{background:#ff8c1a;outline:2px solid #000}'
    + '.imece-okunan{background:#fff3bf!important;color:#000!important;box-shadow:-6px 0 0 #c9a227}';
  (document.head || document.documentElement).appendChild(sabit);
  function uygula(a) {
    var boy = Math.max(60, Math.min(200, +a.boy || 100));
    stil.textContent = 'html{zoom:' + boy + '%}' + (a.gece
      ? 'html{filter:invert(.92) hue-rotate(180deg);background:#fff}img,video,svg,canvas{filter:invert(1) hue-rotate(180deg)}' : '');
  }
  // Ayarlar çerçevenin adında taşınır: sayfa daha çizilmeden uygulanır, gece modunda ekran beyaz parlamaz.
  try { if (window.name && window.name.charAt(0) === '{') uygula(JSON.parse(window.name)); } catch (e) {}

  // ---- Sadeleştirme: küçük harf + noktasız, şapkasız (ISI = ısı = isi). Harf sayısı değişmez. ----
  var TR = { 'I': 'i', 'İ': 'i', 'ı': 'i', 'ç': 'c', 'Ç': 'c', 'ğ': 'g', 'Ğ': 'g', 'ö': 'o', 'Ö': 'o', 'ş': 's', 'Ş': 's', 'ü': 'u', 'Ü': 'u' };
  function sade(s) {
    var out = '', c, k, t;
    for (var i = 0; i < s.length; i++) {
      c = s.charAt(i);
      if (TR[c]) { out += TR[c]; continue; }
      k = s.charCodeAt(i);
      if (k >= 0xC0 && k < 0x250) { t = c.normalize('NFD').charAt(0); if (t !== c && /[A-Za-z]/.test(t)) c = t; }
      t = c.toLowerCase();
      out += t.length === 1 ? t : c;
    }
    return out;
  }
  var HARF;
  try { HARF = new RegExp('[\\p{L}\\p{N}]', 'u'); } catch (e) { HARF = /[A-Za-z0-9À-￿]/; }
  function harfMi(c) { return !!c && HARF.test(c); }
  function ebeveynleriAc(el) {  // kapalı bir bölümün (details) içindeyse görünür olsun
    for (var p = el; p && p !== document.body; p = p.parentNode) if (p.tagName === 'DETAILS' && !p.open) p.open = true;
  }
  var ATLA = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEMPLATE: 1, TEXTAREA: 1 };

  // ---- Sayfada bul ----
  var isaretler = [], simdi = -1;
  function bulTemizle() {
    for (var i = 0; i < isaretler.length; i++) {
      var m = isaretler[i], p = m.parentNode;
      if (!p) continue;
      p.replaceChild(document.createTextNode(m.textContent), m);
      p.normalize();
    }
    isaretler = []; simdi = -1;
  }
  // kelimeler: [{k: sadeleştirilecek metin, onek: true/false}] → kelime başından arar; onek ise kelimenin sonuna kadar alır.
  // kelimeler yoksa q düz metin olarak, kelimenin neresinde olursa olsun aranır.
  function eslesmeler(metin, q, kelimeler) {
    var out = [], p, i;
    if (!kelimeler) {
      for (p = metin.indexOf(q); p >= 0 && out.length < 500; p = metin.indexOf(q, p + q.length)) out.push([p, p + q.length]);
      return out;
    }
    for (i = 0; i < kelimeler.length; i++) {
      var k = kelimeler[i].k, son;
      for (p = metin.indexOf(k); p >= 0 && out.length < 500; p = metin.indexOf(k, p + 1)) {
        if (p > 0 && harfMi(metin.charAt(p - 1))) continue;
        son = p + k.length;
        if (kelimeler[i].onek) { while (son < metin.length && harfMi(metin.charAt(son))) son++; }
        else if (harfMi(metin.charAt(son))) continue;
        out.push([p, son]);
      }
    }
    out.sort(function (a, b) { return a[0] - b[0] || b[1] - a[1]; });
    var temiz = [], sonraki = 0;
    for (i = 0; i < out.length; i++) if (out[i][0] >= sonraki) { temiz.push(out[i]); sonraki = out[i][1]; }
    return temiz;
  }
  function bul(q, kelimeler) {
    bulTemizle();
    q = sade(String(q || ''));
    if (kelimeler) {
      kelimeler = kelimeler.map(function (x) { return { k: sade(String(x.k || '')), onek: !!x.onek }; }).filter(function (x) { return x.k; });
      if (!kelimeler.length) kelimeler = null;
    }
    if (!document.body || (!kelimeler && !q)) return gonder({ tur: 'bul-sonuc', adet: 0, sira: 0 });
    var yuru = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null), dugumler = [], n;
    while ((n = yuru.nextNode())) {
      if (n.nodeValue.length && !(n.parentNode && ATLA[n.parentNode.tagName])) dugumler.push(n);
    }
    for (var d = 0; d < dugumler.length && isaretler.length < 3000; d++) {
      var dugum = dugumler[d], e = eslesmeler(sade(dugum.nodeValue), q, kelimeler), yeni = [];
      for (var j = e.length - 1; j >= 0; j--) {  // sondan başa: öndeki konumlar bozulmaz
        var orta = dugum.splitText(e[j][0]);
        orta.splitText(e[j][1] - e[j][0]);
        var m = document.createElement('mark');
        m.className = 'imece-bul';
        orta.parentNode.replaceChild(m, orta);
        m.appendChild(orta);
        yeni.unshift(m);
      }
      isaretler = isaretler.concat(yeni);
    }
    bulGit(0, true);
  }
  function bulGit(i, ilk) {
    if (!isaretler.length) return gonder({ tur: 'bul-sonuc', adet: 0, sira: 0 });
    if (simdi >= 0 && isaretler[simdi]) isaretler[simdi].classList.remove('imece-simdi');
    simdi = ((i % isaretler.length) + isaretler.length) % isaretler.length;
    var m = isaretler[simdi];
    m.classList.add('imece-simdi');
    ebeveynleriAc(m);
    try { m.scrollIntoView({ block: 'center' }); } catch (e) { m.scrollIntoView(); }
    gonder({ tur: 'bul-sonuc', adet: isaretler.length, sira: simdi + 1, sinir: isaretler.length >= 3000 });
  }

  // ---- İçindekiler: sayfanın bölüm başlıkları ----
  var basliklar = [];
  function baslikTopla() {
    basliklar = [];
    var liste = [], hs = document.body ? document.body.querySelectorAll('h2, h3, h4') : [];
    for (var i = 0; i < hs.length && liste.length < 400; i++) {
      var ad = (hs[i].textContent || '').replace(/\s+/g, ' ').trim();
      if (!ad) continue;
      basliklar.push(hs[i]);
      liste.push({ d: +hs[i].tagName.charAt(1), ad: ad.slice(0, 160) });
    }
    gonder({ tur: 'basliklar', liste: liste });
  }

  // ---- Sesli okuma: okunacak paragraflar arayüze verilir, ses arayüzde üretilir ----
  var okunacak = [], okunan = null;
  var BLOK = 'p, li, h1, h2, h3, h4, blockquote, dd, dt';
  var OKUNMAZ = 'table, nav, .navbox, .infobox, .reference, .mw-ref, .references, .reflist, .mw-editsection, .noprint, .hatnote, .thumbcaption, figure, sup, style, script';
  function okunacakMetin(el) {
    var k = el.cloneNode(true), at = k.querySelectorAll(OKUNMAZ);
    for (var i = 0; i < at.length; i++) if (at[i].parentNode) at[i].parentNode.removeChild(at[i]);
    return (k.textContent || '').replace(/\[\s*\d+\s*\]/g, ' ').replace(/\s+/g, ' ').trim();
  }
  function metinTopla() {
    okunacak = [];
    var parcalar = [], bas = -1, els = document.body ? document.body.querySelectorAll(BLOK) : [];
    for (var i = 0; i < els.length && parcalar.length < 4000; i++) {
      var el = els[i];
      if (el.closest(OKUNMAZ) || el.querySelector(BLOK)) continue;      // tablo, dipnot, gezinme kutusu; iç içe bloklar
      if (!el.getClientRects().length) continue;                         // görünmeyen (gizli) parça
      var t = okunacakMetin(el);
      if (t.length < 2) continue;
      if (bas < 0 && el.getBoundingClientRect().bottom > 0) bas = parcalar.length;  // ekranda görünen ilk paragraf
      okunacak.push(el);
      parcalar.push(t.slice(0, 5000));
    }
    gonder({ tur: 'metin', parcalar: parcalar, bas: Math.max(0, bas), dil: (document.documentElement.lang || '').toLowerCase() });
  }
  function okunanIsaretle(i) {
    if (okunan) okunan.classList.remove('imece-okunan');
    okunan = okunacak[i] || null;
    if (okunan) {
      okunan.classList.add('imece-okunan');
      ebeveynleriAc(okunan);
      try { okunan.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (e) { okunan.scrollIntoView(); }
    }
  }

  window.addEventListener('message', function (ev) {
    var d = ev.data;
    if (ev.source !== ust || !d || d.imece !== 1) return;
    if (d.tur === 'ayar') { uygula(d); try { window.name = JSON.stringify({ boy: d.boy, gece: d.gece }); } catch (e) {} }
    else if (d.tur === 'geri') history.back();
    else if (d.tur === 'ileri') history.forward();
    else if (d.tur === 'bul') bul(d.q, d.kelimeler);
    else if (d.tur === 'bul-git') bulGit(simdi + (d.yon < 0 ? -1 : 1));
    else if (d.tur === 'baslik-git') {
      var h = basliklar[d.i];
      if (h) { ebeveynleriAc(h); try { h.scrollIntoView({ block: 'start' }); } catch (e) { h.scrollIntoView(); } }
    }
    else if (d.tur === 'metin-iste') metinTopla();
    else if (d.tur === 'okunan') okunanIsaretle(d.i);
  });

  // Bağlantılar: internete gidenler açılmaz (çevrimdışıyız), yeni sekme isteyenler aynı yerde açılır.
  function tikla(ev) {
    var a = ev.target && ev.target.closest && ev.target.closest('a[href]');
    if (!a) return;
    var h = a.getAttribute('href') || '';
    if (/^(https?:)?\/\//i.test(h) && a.host !== location.host) { ev.preventDefault(); gonder({ tur: 'dis', adres: a.href }); }
    else if ((ev.ctrlKey || ev.metaKey || ev.button === 1) && a.host === location.host && a.pathname.indexOf('/zim/') === 0
             && !(h.charAt(0) === '#')) {
      // Ctrl ile ya da tekerlek düğmesiyle basılan kitap içi bağlantı: İmece'nin okuyucusunda yeni sekmede açılır.
      ev.preventDefault(); gonder({ tur: 'yeni-sekme', yol: a.pathname });
    }
    else if (ev.button === 1) ev.preventDefault();  // tekerlek düğmesi tarayıcı sekmesi açmasın
    else if (a.target && a.target !== '_self') a.target = '_self';
  }
  document.addEventListener('click', tikla, true);
  document.addEventListener('auxclick', tikla, true);
  // Ctrl+F: İmece'nin kendi "sayfada bul" çubuğu açılır (Türkçe harflere takılmaz).
  document.addEventListener('keydown', function (ev) {
    if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && (ev.key === 'f' || ev.key === 'F')) { ev.preventDefault(); gonder({ tur: 'bul-ac' }); }
  }, true);

  function bildir() {
    gonder({ tur: 'sayfa', yol: location.pathname, baslik: (document.title || '').slice(0, 300) });
    baslikTopla();
  }
  gonder({ tur: 'hazir' });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bildir); else bildir();
  window.addEventListener('pageshow', function (e) { if (e.persisted) bildir(); });
})();
