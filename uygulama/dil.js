// İmece — isteğe bağlı İngilizce arayüz katmanı.
// Türkçe metin kaynaktır ve değişmez; bu betik yalnızca ekranda görünen yazıyı sözlükten (dil-en.js) çevirir.
// Sözlükte karşılığı olmayan yazı Türkçe kalır. Çevrilmeyenler:
//   - rehber bölümleri (her cümlesi kaynağa bağlı; uzman onayı Türkçe metnin özetine bağlanır),
//   - kitapların kendi içeriği (başlıklar, açıklamalar, arama sonuçları, notlar).
(function () {
  var dil = 'tr';
  try { dil = localStorage.getItem('imece-arayuz-dil') === 'en' ? 'en' : 'tr'; } catch (e) {}  // 'imece-dil' Paketler'deki içerik dilidir
  window.imeceDil = dil;
  var dugme = document.getElementById('arayuz-dil');
  if (dugme) [].forEach.call(dugme.children, function (b) {
    b.classList.toggle('aktif', b.dataset.dil === dil);
    b.onclick = function () { try { localStorage.setItem('imece-arayuz-dil', b.dataset.dil); } catch (e) {} location.reload(); };
  });
  if (dil !== 'en' || !window.IMECE_EN) return;

  var SOZ = IMECE_EN.soz, KALIP = IMECE_EN.kalip || [], ATLA = IMECE_EN.atla || '';
  var REHBER = (window.REHBER_KAYNAK || {}).bolumler || {};
  var HARF = 'A-Za-zÇĞİÖŞÜçğıöşüÂâÎîÛû0-9';
  function kacis(k) { return k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  // Parça eşleşmesi: yalnızca 8 harf ve üstü anahtarlar, kelime sınırında (kısa kelimeler içerikte yanlış yere düşer).
  var parcalar = Object.keys(SOZ).filter(function (k) { return k.length >= 8; }).sort(function (a, b) { return b.length - a.length; })
    .map(function (k) {
      var sol = new RegExp('[' + HARF + ']').test(k.charAt(0)) ? '(^|[^' + HARF + '])' : '()';
      var sag = new RegExp('[' + HARF + ']').test(k.charAt(k.length - 1)) ? '(?=$|[^' + HARF + '])' : '';
      return [new RegExp(sol + kacis(k) + sag, 'g'), SOZ[k]];
    });
  var kalan = window.imeceCevrilmeyen = {};  // çevrildikten sonra hâlâ Türkçe harf taşıyan yazılar (sınama için)
  var islenen = new WeakMap();

  function cevir(v) {
    var k = v.replace(/\s+/g, ' ').trim();
    if (!k || !/[A-Za-zÇĞİÖŞÜçğıöşü]{2}/.test(k)) return null;
    var on = /^\s*/.exec(v)[0], son = /\s*$/.exec(v)[0], s = k, i;
    if (Object.prototype.hasOwnProperty.call(SOZ, k)) return on + SOZ[k] + son;
    for (i = 0; i < KALIP.length; i++) if (KALIP[i][0].test(s)) { s = s.replace(KALIP[i][0], KALIP[i][1]); break; }
    for (i = 0; i < parcalar.length; i++) {
      (function (p) { s = s.replace(p[0], function (m, once) { return (once || '') + p[1]; }); })(parcalar[i]);
    }
    if (/[çğıöşüÇĞİÖŞÜ]/.test(s)) kalan[k] = s;
    return s === k ? null : on + s + son;
  }
  window.imeceCevir = cevir;

  function atlanir(el, oz) {  // oz: öznitelik çevirisi (yazı kutusunun kendi ipucu çevrilir, içine yazılan çevrilmez)
    if (!el || el.closest('script,style,iframe,.dil-notu') || (!oz && el.closest('textarea'))) return true;
    if (ATLA && el.closest(ATLA)) return true;
    var sec = el.closest('section');
    return !!(sec && REHBER[sec.id] && !el.closest('h2'));  // rehber gövdesi çevrilmez
  }
  function yaziDugumu(n) {
    if (islenen.get(n) === n.nodeValue || atlanir(n.parentElement)) return;
    var y = cevir(n.nodeValue);
    if (y != null) n.nodeValue = y;
    islenen.set(n, n.nodeValue);
  }
  var OZ = ['placeholder', 'title', 'aria-label'];
  function oge(el) {
    if (el.nodeType !== 1) return;
    OZ.forEach(function (a) {
      if (el.hasAttribute(a) && el.getAttribute('data-cv-' + a) !== el.getAttribute(a) && !atlanir(el, true)) {
        var y = cevir(el.getAttribute(a));
        if (y != null) el.setAttribute(a, y);
        el.setAttribute('data-cv-' + a, el.getAttribute(a));
      }
    });
  }
  function gez(kok) {
    if (kok.nodeType === 3) return yaziDugumu(kok);
    if (kok.nodeType !== 1) return;
    oge(kok);
    var w = document.createTreeWalker(kok, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, null), n;
    while ((n = w.nextNode())) { if (n.nodeType === 3) yaziDugumu(n); else oge(n); }
  }

  // Rehber bölümlerinin başına: neden Türkçe kaldığı ve ne durumda olduğu
  Object.keys(REHBER).forEach(function (id) {
    var sec = document.getElementById(id), h = sec && sec.querySelector('h2');
    if (!h || sec.querySelector('.dil-notu')) return;
    var d = document.createElement('div');
    d.className = 'uyari dil-notu';
    d.textContent = IMECE_EN.rehberNotu;
    h.insertAdjacentElement('afterend', d);
  });

  document.documentElement.lang = 'en';
  if (SOZ[document.title]) document.title = SOZ[document.title];
  gez(document.body);
  new MutationObserver(function (l) {
    l.forEach(function (m) {
      if (m.type === 'characterData') yaziDugumu(m.target);
      else if (m.type === 'attributes') oge(m.target);
      else [].forEach.call(m.addedNodes, gez);
    });
  }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: OZ });

  // Onay ve uyarı kutuları: satır satır çevrilir
  function ileti(m) { return String(m).split('\n').map(function (s) { var y = cevir(s); return y == null ? s : y; }).join('\n'); }
  var c0 = window.confirm, a0 = window.alert;
  window.confirm = function (m) { return c0.call(window, ileti(m)); };
  window.alert = function (m) { return a0.call(window, ileti(m)); };
})();
