// İmece — Oyunlar: satranç, sudoku, mangala. Hepsi bu dosyadaki kendi kodumuzdur; internet ya da başka bir kitaplık istemez.
// Oyun kuralları (hamle üretimi, bulmaca üretimi) arayüzden ayrı tutuldu ve sınanabilsin diye dışarı açıldı:
//   window.imeceSatranc, window.imeceSudoku, window.imeceMangala.  Arayüz: window.imeceOyun(ad, öge).
(function () {
  'use strict';

  /* ================================================================ SATRANÇ ================================================================
     Tahta 64 karelik bir dizi: 0 = a8 … 63 = h1. Beyaz taşlar büyük harf (KQRBNP), siyahlar küçük harf.
     Bilinen eksikler: piyon son sıraya varınca kendiliğinden vezir olur (taş seçtirmez); üç kez yineleme ve
     50 hamle beraberliği sayılmaz. Bilgisayara karşı oyun yok: aynı cihazda iki kişi oynar. */
  var YON = { N: [[-2, -1], [-2, 1], [-1, -2], [-1, 2], [1, -2], [1, 2], [2, -1], [2, 1]], B: [[-1, -1], [-1, 1], [1, -1], [1, 1]], R: [[-1, 0], [1, 0], [0, -1], [0, 1]] };
  YON.Q = YON.B.concat(YON.R); YON.K = YON.Q;
  var BASLANGIC = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -';
  function renk(p) { return p ? (p === p.toUpperCase() ? 'w' : 'b') : ''; }
  function fenOku(f) {
    var p = f.split(' '), t = [];
    p[0].split('/').forEach(function (sat) { sat.split('').forEach(function (c) { if (/\d/.test(c)) for (var i = 0; i < +c; i++) t.push(''); else t.push(c); }); });
    return { t: t, sira: p[1] || 'w', rok: (p[2] && p[2] !== '-') ? p[2] : '', ep: (p[3] && p[3] !== '-') ? (8 - (+p[3][1])) * 8 + (p[3].charCodeAt(0) - 97) : -1 };
  }
  function saldiri(S, k, r) {  // k karesi r rengindeki bir taşın tehdidi altında mı
    var t = S.t, s = k >> 3, c = k & 7, w = r === 'w', i, d, y, x, p;
    var ps = w ? s + 1 : s - 1, P = w ? 'P' : 'p', N = w ? 'N' : 'n', K = w ? 'K' : 'k', B = w ? 'B' : 'b', R = w ? 'R' : 'r', Q = w ? 'Q' : 'q';
    if (ps >= 0 && ps < 8) { if (c > 0 && t[ps * 8 + c - 1] === P) return true; if (c < 7 && t[ps * 8 + c + 1] === P) return true; }
    for (i = 0; i < 8; i++) {
      y = s + YON.N[i][0]; x = c + YON.N[i][1]; if (y >= 0 && y < 8 && x >= 0 && x < 8 && t[y * 8 + x] === N) return true;
      y = s + YON.K[i][0]; x = c + YON.K[i][1]; if (y >= 0 && y < 8 && x >= 0 && x < 8 && t[y * 8 + x] === K) return true;
    }
    for (i = 0; i < 8; i++) {
      d = YON.Q[i]; y = s + d[0]; x = c + d[1];
      while (y >= 0 && y < 8 && x >= 0 && x < 8) { p = t[y * 8 + x]; if (p) { if (p === Q || p === (i < 4 ? B : R)) return true; break; } y += d[0]; x += d[1]; }
    }
    return false;
  }
  function sozde(S) {  // şah güvenliğine bakmadan bütün hamleler
    var t = S.t, r = S.sira, w = r === 'w', h = [];
    function ekle(f, z, terfi) { if (terfi) ['Q', 'R', 'B', 'N'].forEach(function (x) { h.push({ f: f, t: z, terfi: x }); }); else h.push({ f: f, t: z }); }
    for (var k = 0; k < 64; k++) {
      var p = t[k]; if (!p || renk(p) !== r) continue;
      var s = k >> 3, c = k & 7, u = p.toUpperCase();
      if (u === 'P') {
        var yon = w ? -1 : 1, ilk = w ? 6 : 1, son = w ? 0 : 7, y = s + yon;
        if (y < 0 || y > 7) continue;
        if (!t[y * 8 + c]) { ekle(k, y * 8 + c, y === son); if (s === ilk && !t[(s + 2 * yon) * 8 + c]) h.push({ f: k, t: (s + 2 * yon) * 8 + c, cift: 1 }); }
        for (var x = c - 1; x <= c + 1; x += 2) {
          if (x < 0 || x > 7) continue;
          var z = y * 8 + x;
          if (t[z] && renk(t[z]) !== r) ekle(k, z, y === son); else if (z === S.ep) h.push({ f: k, t: z, ep: 1 });
        }
      } else {
        var kayar = u !== 'N' && u !== 'K';
        for (var i = 0; i < YON[u].length; i++) {
          var d = YON[u][i], yy = s + d[0], xx = c + d[1];
          while (yy >= 0 && yy < 8 && xx >= 0 && xx < 8) {
            var zz = yy * 8 + xx;
            if (!t[zz]) h.push({ f: k, t: zz }); else { if (renk(t[zz]) !== r) h.push({ f: k, t: zz }); break; }
            if (!kayar) break;
            yy += d[0]; xx += d[1];
          }
        }
      }
    }
    var ks = (w ? 7 : 0) * 8 + 4, dus = w ? 'b' : 'w';  // rok: şah ve geçtiği kareler tehdit altında olmamalı, arası boş olmalı
    if (t[ks] === (w ? 'K' : 'k') && !saldiri(S, ks, dus)) {
      if (S.rok.indexOf(w ? 'K' : 'k') >= 0 && !t[ks + 1] && !t[ks + 2] && t[ks + 3] === (w ? 'R' : 'r') && !saldiri(S, ks + 1, dus) && !saldiri(S, ks + 2, dus)) h.push({ f: ks, t: ks + 2, rok: 'k' });
      if (S.rok.indexOf(w ? 'Q' : 'q') >= 0 && !t[ks - 1] && !t[ks - 2] && !t[ks - 3] && t[ks - 4] === (w ? 'R' : 'r') && !saldiri(S, ks - 1, dus) && !saldiri(S, ks - 2, dus)) h.push({ f: ks, t: ks - 2, rok: 'q' });
    }
    return h;
  }
  function oyna(S, h) {
    var t = S.t.slice(), p = t[h.f], w = S.sira === 'w', rok = S.rok;
    t[h.t] = h.terfi ? (w ? h.terfi : h.terfi.toLowerCase()) : p; t[h.f] = '';
    if (h.ep) t[h.t + (w ? 8 : -8)] = '';
    if (h.rok === 'k') { t[h.t - 1] = t[h.t + 1]; t[h.t + 1] = ''; }
    if (h.rok === 'q') { t[h.t + 1] = t[h.t - 2]; t[h.t - 2] = ''; }
    function sil(x) { rok = rok.replace(x, ''); }
    if (p === 'K') { sil('K'); sil('Q'); } if (p === 'k') { sil('k'); sil('q'); }
    [[63, 'K'], [56, 'Q'], [7, 'k'], [0, 'q']].forEach(function (a) { if (h.f === a[0] || h.t === a[0]) sil(a[1]); });
    return { t: t, sira: w ? 'b' : 'w', rok: rok, ep: h.cift ? (h.f + h.t) / 2 : -1 };
  }
  function sahta(S, r) { var k = S.t.indexOf(r === 'w' ? 'K' : 'k'); return k >= 0 && saldiri(S, k, r === 'w' ? 'b' : 'w'); }
  function hamleler(S) { return sozde(S).filter(function (h) { return !sahta(oyna(S, h), S.sira); }); }
  function perft(S, d) { if (d === 0) return 1; var n = 0, l = hamleler(S); if (d === 1) return l.length; for (var i = 0; i < l.length; i++) n += perft(oyna(S, l[i]), d - 1); return n; }
  window.imeceSatranc = { fen: fenOku, baslangic: BASLANGIC, hamleler: hamleler, oyna: oyna, sahta: sahta, perft: perft };

  var TAS = { K: '♚', Q: '♛', R: '♜', B: '♝', N: '♞', P: '♟' };
  function satrancKur(el) {
    var gecmis = [fenOku(BASLANGIC)], secili = -1, hedefler = [];
    function S() { return gecmis[gecmis.length - 1]; }
    function ciz() {
      var s = S(), l = hamleler(s), sah = sahta(s, s.sira), kim = s.sira === 'w' ? 'Beyaz' : 'Siyah', durum;
      if (!l.length) durum = sah ? 'Şah mat: ' + (s.sira === 'w' ? 'Siyah' : 'Beyaz') + ' kazandı.' : 'Pat: oyun berabere.';
      else durum = 'Sıra: ' + kim + (sah ? ' · Şah!' : '');
      var h = '<div class="oyun-durum" id="st-durum">' + durum + '</div><div class="st-tahta" id="st-tahta">';
      for (var k = 0; k < 64; k++) {
        var p = s.t[k], koyu = ((k >> 3) + (k & 7)) % 2;
        h += '<button data-k="' + k + '" class="st-kare ' + (koyu ? 'koyu' : 'acik') + (k === secili ? ' secili' : '') + (hedefler.indexOf(k) >= 0 ? ' hedef' : '') + (p ? ' ' + (renk(p) === 'w' ? 'beyaz' : 'siyah') : '') + '" aria-label="' + 'abcdefgh'[k & 7] + (8 - (k >> 3)) + '">' + (p ? TAS[p.toUpperCase()] : '') + '</button>';
      }
      h += '</div><div class="satir"><button class="btn ikincil" id="st-geri">Hamleyi geri al</button><button class="btn ikincil" id="st-yeni">Yeni oyun</button></div>'
        + '<p class="alt">Bir taşa, sonra gideceği kareye bas. Gidebileceği kareler işaretlenir. Piyon son sıraya varınca vezir olur. Aynı cihazda iki kişi oynar.</p>';
      el.innerHTML = h;
      el.querySelector('#st-geri').onclick = function () { if (gecmis.length > 1) gecmis.pop(); secili = -1; hedefler = []; ciz(); };
      el.querySelector('#st-yeni').onclick = function () { gecmis = [fenOku(BASLANGIC)]; secili = -1; hedefler = []; ciz(); };
      el.querySelector('#st-tahta').onclick = function (ev) {
        var b = ev.target.closest('[data-k]'); if (!b) return;
        var k = +b.dataset.k, s2 = S(), l2 = hamleler(s2);
        if (secili >= 0 && hedefler.indexOf(k) >= 0) {
          var hm = l2.filter(function (x) { return x.f === secili && x.t === k && (!x.terfi || x.terfi === 'Q'); })[0];
          gecmis.push(oyna(s2, hm)); secili = -1; hedefler = [];
        } else if (s2.t[k] && renk(s2.t[k]) === s2.sira) {
          secili = k; hedefler = l2.filter(function (x) { return x.f === k; }).map(function (x) { return x.t; });
        } else { secili = -1; hedefler = []; }
        ciz();
      };
    }
    ciz();
  }

  /* ================================================================ SUDOKU ================================================================
     Önce rastgele dolu bir tablo üretilir, sonra tek çözümlü kaldığı sürece kareler boşaltılır. */
  function sUygun(g, i, v) {
    var s = (i / 9) | 0, c = i % 9, k, bs = s - s % 3, bc = c - c % 3;
    for (k = 0; k < 9; k++) if (g[s * 9 + k] === v || g[k * 9 + c] === v || g[(bs + ((k / 3) | 0)) * 9 + bc + k % 3] === v) return false;
    return true;
  }
  function sCozumSay(g0, sinir) {  // en çok "sinir" kadar çözüm sayar (tek çözümlü mü diye bakmak için 2 yeter)
    var g = g0.slice(), n = 0;
    (function coz() {
      var en = -1, enAz = 10, i, v, a;
      for (i = 0; i < 81; i++) if (!g[i]) { a = 0; for (v = 1; v <= 9; v++) if (sUygun(g, i, v)) a++; if (a < enAz) { enAz = a; en = i; if (a <= 1) break; } }
      if (en < 0) { n++; return; }
      for (v = 1; v <= 9 && n < sinir; v++) if (sUygun(g, en, v)) { g[en] = v; coz(); g[en] = 0; }
    })();
    return n;
  }
  function rastgele(tohum) { var a = tohum >>> 0; return function () { a = (a + 0x6D2B79F5) >>> 0; var t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  function sUret(bos, tohum) {
    var r = rastgele(tohum == null ? (Date.now() ^ (Math.random() * 1e9)) : tohum), g = new Array(81).fill(0);
    function karistir(a) { for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(r() * (i + 1)), x = a[i]; a[i] = a[j]; a[j] = x; } return a; }
    (function doldur(i) { if (i === 81) return true; var l = karistir([1, 2, 3, 4, 5, 6, 7, 8, 9]); for (var k = 0; k < 9; k++) if (sUygun(g, i, l[k])) { g[i] = l[k]; if (doldur(i + 1)) return true; g[i] = 0; } return false; })(0);
    var cozum = g.slice(), sira = karistir(Array.from({ length: 81 }, function (_, i) { return i; })), kalan = bos;
    for (var i = 0; i < 81 && kalan > 0; i++) { var v = g[sira[i]]; g[sira[i]] = 0; if (sCozumSay(g, 2) !== 1) g[sira[i]] = v; else kalan--; }
    return { bulmaca: g, cozum: cozum };
  }
  function sCakisma(g) {  // kurala aykırı duran karelerin dizinleri
    var out = [];
    for (var i = 0; i < 81; i++) if (g[i]) { var v = g[i]; g[i] = 0; if (!sUygun(g, i, v)) out.push(i); g[i] = v; }
    return out;
  }
  window.imeceSudoku = { uret: sUret, cozumSay: sCozumSay, cakisma: sCakisma };

  function sudokuKur(el) {
    var Z = { kolay: 36, orta: 46, zor: 52 }, zor = 'orta', o, g, secili = -1;
    function yeni() { o = sUret(Z[zor]); g = o.bulmaca.slice(); secili = -1; ciz(); }
    function ciz() {
      var cak = sCakisma(g), dolu = g.every(function (v) { return v; }), bitti = dolu && !cak.length;
      var h = '<div class="satir">' + Object.keys(Z).map(function (z) { return '<button class="btn ikincil' + (z === zor ? ' aktif' : '') + '" data-zor="' + z + '">' + { kolay: 'Kolay', orta: 'Orta', zor: 'Zor' }[z] + '</button>'; }).join('') + '<button class="btn" id="sd-yeni">Yeni bulmaca</button></div>'
        + '<div class="oyun-durum" id="sd-durum">' + (bitti ? 'Tebrikler, bulmaca çözüldü.' : (cak.length ? 'Kurala uymayan ' + cak.length + ' kare işaretli.' : 'Boş kare: ' + g.filter(function (v) { return !v; }).length)) + '</div><div class="sd-tahta" id="sd-tahta">';
      for (var i = 0; i < 81; i++) h += '<button data-i="' + i + '" class="sd-kare' + (o.bulmaca[i] ? ' verili' : '') + (i === secili ? ' secili' : '') + (cak.indexOf(i) >= 0 ? ' hata' : '') + ((i % 9) % 3 === 2 && i % 9 !== 8 ? ' sagc' : '') + (((i / 9) | 0) % 3 === 2 && i < 72 ? ' altc' : '') + '">' + (g[i] || '') + '</button>';
      h += '</div><div class="sd-rakam" id="sd-rakam">' + [1, 2, 3, 4, 5, 6, 7, 8, 9].map(function (v) { return '<button class="btn ikincil" data-v="' + v + '">' + v + '</button>'; }).join('') + '<button class="btn ikincil" data-v="0">Sil</button></div>'
        + '<p class="alt">Bir kareye, sonra bir rakama bas. Her satırda, her sütunda ve her 3×3 kutuda 1’den 9’a bütün rakamlar birer kez bulunmalı. Her bulmacanın tek bir çözümü vardır.</p>';
      el.innerHTML = h;
      el.querySelector('#sd-yeni').onclick = yeni;
      [].forEach.call(el.querySelectorAll('[data-zor]'), function (b) { b.onclick = function () { zor = b.dataset.zor; yeni(); }; });
      el.querySelector('#sd-tahta').onclick = function (ev) { var b = ev.target.closest('[data-i]'); if (!b) return; var i = +b.dataset.i; secili = o.bulmaca[i] ? -1 : i; ciz(); };
      el.querySelector('#sd-rakam').onclick = function (ev) { var b = ev.target.closest('[data-v]'); if (!b || secili < 0) return; g[secili] = +b.dataset.v; ciz(); };
    }
    yeni();
  }

  /* ================================================================ MANGALA ================================================================
     Kuyular: 0–5 birinci oyuncunun, 6 onun haznesi; 7–12 ikinci oyuncunun, 13 onun haznesi. Her kuyuda 4 taşla başlanır.
     Kurallar: seçilen kuyudaki taşlar alınır; birden çoksa biri aynı kuyuya bırakılır, kalanlar saat yönünün tersine birer
     birer dağıtılır (rakibin haznesi atlanır); tek taş varsa yandaki kuyuya konur. Son taş: kendi haznene gelirse yine sen
     oynarsın; rakibin kuyusundaki taşları çift yaparsa o kuyudakileri alırsın; kendi boş kuyuna gelirse ve karşısı doluysa
     ikisini de alırsın. Bir oyuncunun kuyuları boşalınca oyun biter; kuyularını boşaltan, rakibin kuyularında kalanları alır. */
  function mYeni() { return { c: [4, 4, 4, 4, 4, 4, 0, 4, 4, 4, 4, 4, 4, 0], sira: 0, bitti: false }; }
  function mOyna(S, i) {
    var o = S.sira, benim = o ? [7, 12] : [0, 5];
    if (S.bitti || i < benim[0] || i > benim[1] || !S.c[i]) return null;
    var c = S.c.slice(), hazne = o ? 13 : 6, rakip = o ? 6 : 13, el = c[i], k = i, yine = false;
    c[i] = 0;
    if (el > 1) { c[i] = 1; el--; }
    while (el > 0) { k = (k + 1) % 14; if (k === rakip) continue; c[k]++; el--; }
    if (k === hazne) yine = true;
    else if (k >= benim[0] && k <= benim[1]) { if (c[k] === 1 && c[12 - k] > 0) { c[hazne] += c[12 - k] + 1; c[k] = 0; c[12 - k] = 0; } }
    else if (c[k] % 2 === 0) { c[hazne] += c[k]; c[k] = 0; }
    function bos(a) { for (var j = a; j < a + 6; j++) if (c[j]) return false; return true; }
    var bitti = false;
    if (bos(0) || bos(7)) {  // kuyuları boşalan oyuncu, rakibin kuyularında kalanları alır
      var bosalan = bos(0) ? 0 : 1, kalan = 0, a = bosalan ? 0 : 7;
      for (var j = a; j < a + 6; j++) { kalan += c[j]; c[j] = 0; }
      c[bosalan ? 13 : 6] += kalan; bitti = true;
    }
    return { c: c, sira: bitti ? o : (yine ? o : 1 - o), bitti: bitti, yine: yine && !bitti };
  }
  window.imeceMangala = { yeni: mYeni, oyna: mOyna };

  function mangalaKur(el) {
    var S = mYeni(), AD = ['1. oyuncu (alt)', '2. oyuncu (üst)'];
    function ciz() {
      var c = S.c, durum = S.bitti ? ('Oyun bitti: ' + (c[6] === c[13] ? 'berabere' : AD[c[6] > c[13] ? 0 : 1] + ' kazandı') + ' (' + c[6] + ' – ' + c[13] + ').') : 'Sıra: ' + AD[S.sira] + (S.yine ? ' · son taş hazneye geldi, yine oynuyor' : '');
      function kuyu(i) { var benim = !S.bitti && (S.sira ? i >= 7 : i <= 5) && c[i] > 0; return '<button class="mg-kuyu' + (benim ? ' oynar' : '') + '" data-i="' + i + '"' + (benim ? '' : ' disabled') + '>' + c[i] + '</button>'; }
      var ust = '', alt = '', i;
      for (i = 12; i >= 7; i--) ust += kuyu(i);
      for (i = 0; i <= 5; i++) alt += kuyu(i);
      el.innerHTML = '<div class="oyun-durum" id="mg-durum">' + durum + '</div><div class="mg-tahta" id="mg-tahta"><div class="mg-hazne" id="mg-h2">' + c[13] + '</div><div class="mg-orta"><div class="mg-sira">' + ust + '</div><div class="mg-sira">' + alt + '</div></div><div class="mg-hazne" id="mg-h1">' + c[6] + '</div></div>'
        + '<div class="satir"><button class="btn ikincil" id="mg-yeni">Yeni oyun</button></div>'
        + '<p class="alt">Kendi sırandaki dolu kuyulardan birine bas. Taşlar saat yönünün tersine dağıtılır: birden çok taş varsa biri aynı kuyuda kalır; tek taş varsa yandaki kuyuya geçer. Son taş kendi haznene gelirse yine sen oynarsın; rakibin kuyusundaki taşları çift yaparsa o taşları alırsın; kendi boş kuyuna gelir ve karşısı doluysa ikisini de alırsın. Bir tarafın kuyuları boşalınca oyun biter; kuyularını boşaltan, karşıda kalan taşları da alır. Haznesinde en çok taş olan kazanır.</p>';
      el.querySelector('#mg-yeni').onclick = function () { S = mYeni(); ciz(); };
      el.querySelector('#mg-tahta').onclick = function (ev) { var b = ev.target.closest('[data-i]'); if (!b) return; var y = mOyna(S, +b.dataset.i); if (y) { S = y; ciz(); } };
    }
    ciz();
  }

  /* ================================================================ ortak ================================================================ */
  var st = document.createElement('style');
  st.textContent = '.oyun-durum{font:700 14px "Courier New",monospace;letter-spacing:1px;text-transform:uppercase;margin:6px 0 10px}'
    + '.st-tahta{display:grid;grid-template-columns:repeat(8,1fr);width:min(100%,480px);border:3px solid var(--yazi)}'
    + '.st-kare{aspect-ratio:1;border:0;padding:0;font-size:clamp(22px,6.5vw,40px);line-height:1;cursor:pointer}'
    + '.st-kare.acik{background:#d9cfa6}.st-kare.koyu{background:#8a8457}.st-kare.beyaz{color:#fbf8ea;text-shadow:0 0 2px #000,0 0 2px #000}.st-kare.siyah{color:#151515}'
    + '.st-kare.secili{outline:4px solid #c0392b;outline-offset:-4px}.st-kare.hedef{box-shadow:inset 0 0 0 5px rgba(192,57,43,.75)}'
    + '.sd-tahta{display:grid;grid-template-columns:repeat(9,1fr);width:min(100%,430px);border:3px solid var(--yazi);margin-bottom:10px}'
    + '.sd-kare{aspect-ratio:1;border:1px solid var(--cizgi);background:var(--kagit);color:var(--yazi);font:400 clamp(15px,4.5vw,22px) "Courier New",monospace;padding:0;cursor:pointer}'
    + '.sd-kare.verili{font-weight:800;background:var(--kagit2);cursor:default}.sd-kare.secili{outline:3px solid #c0392b;outline-offset:-3px}.sd-kare.hata{color:#c0392b;font-weight:800}'
    + '.sd-kare.sagc{border-right:3px solid var(--yazi)}.sd-kare.altc{border-bottom:3px solid var(--yazi)}'
    + '.sd-rakam{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}.sd-rakam .btn{min-width:42px}'
    + '.mg-tahta{display:flex;gap:8px;align-items:stretch;width:min(100%,640px);border:3px solid var(--yazi);padding:8px;background:var(--kagit2)}'
    + '.mg-hazne{flex:0 0 14%;display:flex;align-items:center;justify-content:center;border:2px solid var(--yazi);font:800 26px "Courier New",monospace}'
    + '.mg-orta{flex:1;display:flex;flex-direction:column;gap:8px}.mg-sira{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}'
    + '.mg-kuyu{aspect-ratio:1;border:2px solid var(--yazi);border-radius:50%;background:var(--kagit);color:var(--yazi);font:800 clamp(15px,4vw,22px) "Courier New",monospace;padding:0}'
    + '.mg-kuyu.oynar{cursor:pointer;background:var(--haki);color:#f1ecd6}.mg-kuyu:disabled{opacity:.75}';
  document.head.appendChild(st);
  window.imeceOyun = function (ad, el) { ({ satranc: satrancKur, sudoku: sudokuKur, mangala: mangalaKur })[ad](el); };
})();
