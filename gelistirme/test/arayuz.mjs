// İmece arayüz senaryoları: gerçek Chrome'u görünmez kipte, geçici profille sürer.
// Kullanım: node arayuz.mjs [--port 8642] [--json çıktı.json] [--resim klasör]
// Ek paket gerekmez (Node 22+). Kullanıcının kendi Chrome profiline dokunmaz.
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync, existsSync, mkdirSync, copyFileSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';

const arg = (ad, v) => { const i = process.argv.indexOf(ad); return i > 0 ? process.argv[i + 1] : v; };
const PORT = +arg('--port', 8642), TABAN = `http://127.0.0.1:${PORT}`, RESIM = arg('--resim', null), CDP = 9333 + (PORT % 50);
const CHROME = ['C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/chromium', '/usr/bin/google-chrome'].find(existsSync);
const profil = mkdtempSync(join(tmpdir(), 'imece-chrome-'));
const tarayici = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${CDP}`, `--user-data-dir=${profil}`, '--no-first-run',
  '--no-default-browser-check', '--window-size=1100,800', '--lang=tr', 'about:blank'], { stdio: 'ignore' });
const bekle = ms => new Promise(r => setTimeout(r, ms));

let hedef;
for (let i = 0; i < 60 && !hedef; i++) {
  await bekle(250);
  try { hedef = (await (await fetch(`http://127.0.0.1:${CDP}/json/list`)).json()).find(t => t.type === 'page'); } catch { }
}
const ws = new WebSocket(hedef.webSocketDebuggerUrl);
await new Promise(r => ws.addEventListener('open', r));
let sira = 0; const bekleyen = new Map(); const cerceveler = []; // {oturum, baglam, kimlik}
let anaCerceve = null; const konsol = [];
let diyalogKabul = false; const diyaloglar = []; // sayfanın açtığı onay kutuları (confirm): yazısı ve verilecek yanıt
ws.addEventListener('message', ev => {
  const m = JSON.parse(ev.data);
  if (m.method === 'Page.javascriptDialogOpening') { diyaloglar.push(m.params.message); gonder('Page.handleJavaScriptDialog', { accept: diyalogKabul }).catch(() => { }); }
  if (m.id && bekleyen.has(m.id)) { const [coz, red] = bekleyen.get(m.id); bekleyen.delete(m.id); m.error ? red(new Error(m.error.message)) : coz(m.result); return; }
  if (m.method === 'Target.attachedToTarget') { // ayrı süreçte çalışan çerçeve (yalıtılmış kitap sayfası)
    const o = m.params.sessionId;
    gonder('Runtime.enable', {}, o).catch(() => { });
  }
  if (m.method === 'Runtime.executionContextCreated') {
    const c = m.params.context, ana = !m.sessionId && c.auxData && c.auxData.frameId === anaCerceve;
    if (c.auxData && c.auxData.isDefault && !ana) cerceveler.push({ oturum: m.sessionId, baglam: c.id, kimlik: c.uniqueId, kaynak: c.origin });
  }
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') konsol.push(m.params.args.map(a => a.value || a.description).join(' '));
  if (m.method === 'Runtime.exceptionThrown') konsol.push('İSTİSNA: ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
});
function gonder(method, params = {}, sessionId) {
  return new Promise((coz, red) => { const id = ++sira; bekleyen.set(id, [coz, red]); ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) })); });
}
anaCerceve = (await gonder('Page.getFrameTree')).frameTree.frame.id;
await gonder('Page.enable'); await gonder('Runtime.enable');
await gonder('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: true });

async function ana(ifade) { // ana sayfada çalıştır
  const r = await gonder('Runtime.evaluate', { expression: ifade, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error('ana: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
  return r.result.value;
}
async function ic(ifade) { // okuyucu çerçevesinin (kitap sayfası) içinde çalıştır: en son oluşan bağlam
  for (let i = cerceveler.length - 1; i >= 0; i--) {
    const c = cerceveler[i];
    try {
      const r = await gonder('Runtime.evaluate', { expression: ifade, awaitPromise: true, returnByValue: true, contextId: c.baglam }, c.oturum);
      if (r.exceptionDetails) return { hata: r.exceptionDetails.exception?.description || r.exceptionDetails.text };
      return r.result.value;
    } catch { cerceveler.splice(i, 1); }
  }
  return { hata: 'çerçeve bağlamı yok' };
}
let gitSayac = 0;
async function git(yol) { // her seferinde sayfayı baştan yükle (sadece # değişirse tarayıcı yeniden yüklemez)
  await gonder('Page.navigate', { url: TABAN + yol.replace(/(\?|#|$)/, (m) => (m === '?' ? '?t=' + (++gitSayac) + '&' : '?t=' + (++gitSayac) + m)) });
  await bekle(700);
}
const kitapDugme = id => `(document.querySelector('#kitaplar [data-giris="${id}"]')||document.querySelector('#kitaplar [data-ac="${id}"]'))`;
async function kadar(ifade, sure = 6000, nerede = ana) { // koşul doğru olana kadar bekle
  const t0 = Date.now(); let son;
  while (Date.now() - t0 < sure) { try { son = await nerede(ifade); if (son && !son.hata) return son; } catch (e) { son = { hata: e.message }; } await bekle(120); }
  return false;
}
const tikla = sec => ana(`(function(){var x=document.querySelector(${JSON.stringify(sec)});if(!x)return false;x.click();return true})()`);
async function resim(ad) {
  if (!RESIM) return; mkdirSync(RESIM, { recursive: true });
  const r = await gonder('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(RESIM, ad + '.png'), Buffer.from(r.data, 'base64'));
}

const SONUC = [];
const SADECE = (arg('--sadece', '') || '').split(',').filter(Boolean);  // yalnızca bu kodlu senaryolar (ör. --sadece U46)
async function senaryo(kod, ad, f) {
  if (SADECE.length && !SADECE.includes(kod)) return;
  const t0 = Date.now(); let durum, kanit;
  try { [durum, kanit] = await f(); durum = durum === 'ATLANDI' ? durum : (durum ? 'GEÇTİ' : 'KALDI'); }
  catch (e) { durum = 'KALDI'; kanit = 'beklenmeyen hata: ' + e.message; }
  SONUC.push({ kod, ad, durum, kanit, sure: Math.round((Date.now() - t0) / 100) / 10 });
  console.log(`${kod.padEnd(4)} ${durum.padEnd(8)} ${ad}\n       ${kanit}`);
}

const DURUM = await (await fetch(TABAN + '/api/durum')).json();
const KITAPLAR = await (await fetch(TABAN + '/api/kitaplar')).json();
const kb = p => (KITAPLAR.find(k => k.id.includes(p)) || {}).id;
const BUYUK = kb('wikipedia_tr_top') || KITAPLAR[0].id, VIKIKITAP = kb('wikibooks');
const YENI = (await fetch(TABAN + '/api/kitap?k=' + encodeURIComponent(BUYUK))).status === 200;
console.log(`İmece ${DURUM.surum} arayüz senaryoları (${CHROME.split('/').pop()}, görünmez kip)\n`);

await senaryo('U1', 'Kütüphane: kitap kartları ve madde sayıları görünüyor', async () => {
  await git('/uygulama/index.html#kutuphane');
  const n = await kadar(`document.querySelectorAll('#kitaplar .kitap').length`);
  const sayi = await ana(`[].map.call(document.querySelectorAll('#kitaplar .kitap'),function(k){return (k.innerText.match(/([\\d.]+) MADDE/i)||[])[1]||'-'}).join(', ')`);
  await resim('U1-kutuphane');
  return [n === KITAPLAR.length && !sayi.includes('-'), `${n} kart; madde sayıları: ${sayi}`];
});

await senaryo('U2', '"Aç" deyince bizim kitap giriş ekranımız geliyor (paketin ana sayfası değil)', async () => {
  await ana(`${kitapDugme(BUYUK)}.click()`);
  const giris = await kadar(`document.getElementById('kitap-ekran') && !document.getElementById('kitap-ekran').hidden && document.querySelector('.kg-sayi b') && document.querySelector('.kg-sayi b').textContent`, 4000);
  const okuyucu = await ana(`!document.getElementById('okuyucu').hidden`);
  await resim('U2-kitap-girisi');
  if (!giris) return [false, `giriş ekranı yok; okuyucu doğrudan açıldı: ${okuyucu} (kullanıcı paketin "seçme konular" sayfasını görüyor, 50.000 maddenin geri kalanına buradan yol yok)`];
  const harf = await ana(`document.querySelectorAll('[data-kg-harf]:not([disabled])').length`);
  return [true, `giriş ekranında ${giris} madde yazıyor, ${harf} harf düğmesi, arama kutusu: ${await ana(`!!document.getElementById('kg-ara')`)}`];
});

if (YENI) {
  await senaryo('U3', 'Kitap içi arama: Türkçe karaktersiz yazınca da buluyor', async () => {
    await ana(`(function(){var i=document.getElementById('kg-ara');i.value='dunya savasi';i.dispatchEvent(new Event('input'))})()`);
    const ilk = await kadar(`document.querySelector('#kg-sonuc li a') && [].slice.call(document.querySelectorAll('#kg-sonuc li a'),0,4).map(function(a){return a.textContent}).join(' | ')`);
    await resim('U3-arama');
    return [ilk && /Dünya savaşı/i.test(ilk), `"dunya savasi" → ${ilk}`];
  });

  await senaryo('U4', 'Sonuca basınca madde okuyucuda açılıyor: metin, biçim ve başlık yerinde', async () => {
    await tikla('#kg-sonuc li a');
    const metin = await kadar(`document.body && document.body.innerText.length>200 && window.__imece===1 && document.body.innerText.slice(0,70).replace(/\\s+/g,' ')`, 8000, ic);
    const bicim = await ic(`document.styleSheets.length+' stil dosyası, yazı tipi: '+getComputedStyle(document.body).fontFamily.split(',')[0]`);
    const baslik = await kadar(`document.getElementById('ok-baslik').textContent`);
    const dogru = await kadar(`/Dünya savaşı/.test(document.getElementById('ok-baslik').textContent)`);
    await resim('U4-okuyucu');
    return [!!metin && dogru, `çerçevedeki metin: "${metin}…"; ${JSON.stringify(bicim)}; okuyucu başlığı: ${baslik}`];
  });

  await senaryo('U5', 'Okunan madde "Son okunanlar"a yazılıyor', async () => {
    const g = await kadar(`(function(){var g=JSON.parse(localStorage.getItem('imece-gecmis')||'[]')[0];return g&&g.baslik+' @ '+g.yol})()`);
    return [/Dünya savaşı/.test(g || ''), `son okunan: ${g}`];
  });

  await senaryo('U6', 'Yer imi: ☆ → ★, listeye giriyor', async () => {
    await tikla('#ok-yerimi');
    const y = await ana(`document.getElementById('ok-yerimi').textContent+' / '+JSON.parse(localStorage.getItem('imece-yerimi')||'[]').map(function(x){return x.baslik}).join(',')`);
    return [/★/.test(y) && /Dünya savaşı/.test(y), y];
  });

  await senaryo('U7', 'Yazı büyütme ve okuma gece modu yalıtılmış sayfaya ulaşıyor', async () => {
    await tikla('#ok-buyuk'); await tikla('#ok-buyuk');
    const buyuk = await kadar(`/zoom:120%/.test(document.getElementById('imece-stil').textContent)`, 3000, ic);
    await tikla('#ok-gece');
    const gece = await kadar(`/invert/.test(document.getElementById('imece-stil').textContent)`, 3000, ic);
    await resim('U7-gece');
    await tikla('#ok-gece'); await tikla('#ok-kucuk'); await tikla('#ok-kucuk');
    const geri = await kadar(`document.getElementById('imece-stil').textContent==='html{zoom:100%}'`, 3000, ic);
    return [buyuk && gece && geri, `büyütme %120: ${!!buyuk}, gece modu: ${!!gece}, eski haline dönme: ${!!geri}`];
  });

  await senaryo('U8', 'Madde içi bağlantı aynı yerde açılıyor; "Geri" önceki maddeye dönüyor; ayarlar yeni sayfada da geçerli', async () => {
    await tikla('#ok-buyuk');
    const hedefAd = await ic(`(function(){var a=[].filter.call(document.querySelectorAll('a[href]'),function(a){var h=a.getAttribute('href');return h&&!/^(https?:|#|\\/\\/)/.test(h)&&a.textContent.trim().length>3})[0];if(!a)return null;a.click();return a.textContent.trim()})()`);
    const yeni = await kadar(`!/^Dünya savaşı$/.test(document.getElementById('ok-baslik').textContent) && document.getElementById('ok-baslik').textContent`);
    const ayar = await kadar(`window.__imece===1 && /zoom:110%/.test(document.getElementById('imece-stil').textContent)`, 3000, ic);
    await tikla('#ok-geri');
    const donus = await kadar(`/^Dünya savaşı$/.test(document.getElementById('ok-baslik').textContent)`);
    await tikla('#ok-kucuk');
    return [!!yeni && !!ayar && !!donus, `"${hedefAd}" bağlantısı → başlık "${yeni}"; yazı boyutu yeni sayfada korundu: ${!!ayar}; Geri ile dönüş: ${!!donus}`];
  });

  await senaryo('U9', 'İnternete giden bağlantı açılmıyor, uyarı çıkıyor', async () => {
    if ((await ic(`window.__imece===1`)) !== true) return [false, 'okuyucu çerçevesi yüklenmedi'];
    await ic(`(function(){var a=document.createElement('a');a.href='https://example.invalid/dis';a.textContent='dış';document.body.appendChild(a);a.click()})()`);
    const uyari = await kadar(`/internete gidiyor/.test(document.getElementById('ok-baslik').textContent) && document.getElementById('ok-baslik').textContent`, 2500);
    const yerinde = await ic(`location.pathname.indexOf('/zim/')===0`);
    return [!!uyari && yerinde === true, `uyarı: "${uyari}"; sayfa yerinde kaldı: ${yerinde}`];
  });

  await senaryo('U10', 'Yalıtım: kitap sayfasındaki betik arayüze, depoya ve yönetim uçlarına ulaşamıyor', async () => {
    const r = await ic(`(async function(){var o={};
      try{o.arayuz=String(!!window.parent.document)}catch(e){o.arayuz='engellendi'}
      try{localStorage.setItem('x','1');o.depo='AÇIK'}catch(e){o.depo='engellendi'}
      try{var y=await fetch('/api/durdur',{method:'POST',body:'{}'});o.yonetim='yanıt '+y.status}catch(e){o.yonetim='engellendi'}
      try{var d=await fetch('/api/durum');o.okuma='yanıt '+d.status+' okundu: '+(await d.text()).length}catch(e){o.okuma='engellendi'}
      o.kimlik=self.origin;return o})()`);
    const tamam = r && r.arayuz === 'engellendi' && r.depo === 'engellendi' && r.yonetim !== 'yanıt 200' && r.okuma === 'engellendi' && r.kimlik === 'null';
    return [tamam, JSON.stringify(r)];
  });

  await senaryo('U11', 'Kapat → kitap girişine dönülüyor; "Kaldığın yer" düğmesi çıkıyor', async () => {
    await tikla('#ok-kapat');
    const gorunur = await ana(`document.getElementById('okuyucu').hidden && !document.getElementById('kitap-ekran').hidden`);
    await tikla('#kg-kapat');
    const son = await ana(`[].map.call(document.querySelectorAll('#gecmis a'),function(a){return a.textContent}).slice(0,2).join(' | ')`);
    await ana(`${kitapDugme(BUYUK)}.click()`);
    const kaldigin = await kadar(`(function(){var b=[].filter.call(document.querySelectorAll('#kg-ic button'),function(b){return /Kaldığın yer/.test(b.textContent)})[0];return b&&b.textContent})()`);
    return [gorunur && !!kaldigin && son.length > 0, `okuyucu kapandı, giriş ekranı altta duruyordu: ${gorunur}; Kütüphane'de son okunanlar: ${son}; düğme: "${kaldigin}"`];
  });

  await senaryo('U12', 'Harfe basınca o harfin bütün maddeleri geliyor; "Devamını göster" çalışıyor', async () => {
    await tikla('[data-kg-harf="Ç"]');
    const bas = await kadar(`document.getElementById('kg-liste-ad') && document.querySelectorAll('#kg-liste-ic li').length>0 && document.getElementById('kg-liste-ad').textContent`);
    const ilk = await ana(`document.querySelectorAll('#kg-liste-ic li').length+' madde; ilk üçü: '+[].slice.call(document.querySelectorAll('#kg-liste-ic li'),0,3).map(function(l){return l.textContent}).join(', ')`);
    await resim('U12-harf-listesi');
    await tikla('#kg-devam');
    const sonra = await kadar(`document.querySelectorAll('#kg-liste-ic li').length>200 && document.querySelectorAll('#kg-liste-ic li').length`);
    const hepsiC = await ana(`[].every.call(document.querySelectorAll('#kg-liste-ic li'),function(l){return /^[^A-Za-zÇçĞğİıÖöŞşÜü0-9]*[Çç]/.test(l.textContent)})`);
    return [!!bas && sonra > 200 && hepsiC, `başlık: "${bas}"; ${ilk}; devamından sonra ${sonra} madde; hepsi Ç ile başlıyor: ${hepsiC}`];
  });

  await senaryo('U13', '"0–9" ve "Diğer" kovaları: rakamla, tırnakla, başka alfabeyle başlayan maddeler de ulaşılır', async () => {
    await tikla('[data-kg-harf="0-9"]');
    const r1 = await kadar(`/Rakam/.test(document.getElementById('kg-liste-ad').textContent) && document.querySelectorAll('#kg-liste-ic li').length>0 && document.getElementById('kg-liste-ad').textContent+' → '+[].slice.call(document.querySelectorAll('#kg-liste-ic li'),0,3).map(function(l){return l.textContent}).join(', ')`);
    await tikla('[data-kg-harf="#"]');
    const r2 = await kadar(`/Diğer/.test(document.getElementById('kg-liste-ad').textContent) && document.querySelectorAll('#kg-liste-ic li').length>0 && document.getElementById('kg-liste-ad').textContent+' → '+[].slice.call(document.querySelectorAll('#kg-liste-ic li'),0,3).map(function(l){return l.textContent}).join(', ')`);
    const w = await ana(`(function(){var b=document.querySelector('[data-kg-harf="W"]');return b?b.textContent:'W düğmesi yok'})()`);
    return [!!r1 && !!r2 && /\d/.test(w), `${r1} | ${r2} | W düğmesi: ${w}`];
  });

  await senaryo('U14', 'Bölümler: Vikikitap\'ta "Yemek" bölümüne basınca yemek tarifleri listeleniyor', async () => {
    if (!VIKIKITAP) return ['ATLANDI', 'Vikikitap kurulu değil'];
    await tikla('#kg-kapat');
    await ana(`${kitapDugme(VIKIKITAP)}.click()`);
    const bolum = await kadar(`document.querySelectorAll('[data-kg-bolum]').length>0 && document.querySelectorAll('[data-kg-bolum]').length`);
    await ana(`[].filter.call(document.querySelectorAll('[data-kg-bolum]'),function(b){return b.dataset.ad==='Yemek'})[0].click()`);
    const liste = await kadar(`/Yemek/.test((document.getElementById('kg-liste-ad')||{}).textContent||'') && document.querySelectorAll('#kg-liste-ic li').length>0 && document.getElementById('kg-liste-ad').textContent+' → '+[].slice.call(document.querySelectorAll('#kg-liste-ic li'),0,3).map(function(l){return l.textContent}).join(', ')`);
    await resim('U14-bolumler');
    return [bolum > 5 && !!liste, `${bolum} bölüm düğmesi; ${liste}`];
  });

  await senaryo('U15', 'Paketin kendi ana sayfası hâlâ bir düğmeyle açılabiliyor; okuyucudan "Kitap girişi"ne dönülüyor', async () => {
    await ana(`[].filter.call(document.querySelectorAll('#kg-ic button'),function(b){return /Paketin ana sayfası/.test(b.textContent)})[0].click()`);
    const acildi = await kadar(`window.__imece===1 && document.body && document.body.innerText.length>100 && location.pathname`, 8000, ic);
    await tikla('#ok-ana');
    const dondu = await kadar(`document.getElementById('okuyucu').hidden && !document.getElementById('kitap-ekran').hidden && document.getElementById('kg-ust').textContent`);
    return [!!acildi && !!dondu, `paket ana sayfası: ${decodeURIComponent(acildi || '')}; "Kitap girişi" → ${dondu}`];
  });

  await senaryo('U16', 'A–Z Dizin sekmesi: kitap seçince o kitabın A–Z\'si açılıyor', async () => {
    await tikla('#kg-kapat');
    await ana(`document.querySelector('#sekmeler button[data-id="dizin"]').click()`);
    const n = await kadar(`document.querySelectorAll('#dz-kitaplar [data-giris]').length`);
    await tikla('#dz-kitaplar [data-giris]');
    const acik = await kadar(`!document.getElementById('kitap-ekran').hidden && !!document.getElementById('kg-az') && document.getElementById('kg-ust').textContent`);
    await tikla('#kg-kapat');
    return [n === KITAPLAR.length && !!acik, `${n} kitap listelendi; ilki açıldı: ${acik}`];
  });
}

// Okuyucuda belirli bir sayfayı aç (iki sürümde de çalışır: sayfaya geçici bir bağlantı ekleyip tıklar).
const okuyucudaAc = (id, yol) => ana(`(function(){var a=document.createElement('a');a.href='#';a.dataset.ac=${JSON.stringify(id)};a.dataset.yol=${JSON.stringify(yol)};document.body.appendChild(a);a.click();a.remove()})()`);

await senaryo('U23', 'Resimli paket: maddedeki resimler okuyucuda yükleniyor', async () => {
  const k = kb('_maxi');
  if (!k) return ['ATLANDI', 'Resimli (maxi) paket kurulu değil'];
  await git('/uygulama/index.html#kutuphane');
  let en = null;
  for (let i = 0; i < 6 && !(en && en.yuklu >= 2); i++) {
    const r = await (await fetch(`${TABAN}/api/rastgele?k=${encodeURIComponent(k)}`)).json();
    await okuyucudaAc(k, r.yol);
    // Sayfa aşağıdaki resimleri görünene kadar yüklemez ("tembel yükleme"); sınamak için hepsini hemen yüklet.
    await kadar(`document.readyState==='complete' && location.pathname.indexOf('/zim/')===0`, 8000, ic);
    await ic(`[].forEach.call(document.images,function(i){i.loading='eager'})`);
    const s = await kadar(`[].every.call(document.images,function(i){return i.complete}) && JSON.stringify({yol:decodeURIComponent(location.pathname.split('/').pop()),toplam:document.images.length,yuklu:[].filter.call(document.images,function(i){return i.naturalWidth>0}).length})`, 10000, ic);
    if (s) { const o = JSON.parse(s); if (!en || o.yuklu > en.yuklu) en = o; }
  }
  await resim('U23-resimli-madde');
  return [en && en.yuklu >= 1 && en.yuklu === en.toplam, en ? `"${en.yol}" maddesinde ${en.toplam} resimden ${en.yuklu} tanesi yüklendi` : 'madde açılamadı'];
});

await senaryo('U24', 'PhET simülasyonu (betik ağırlıklı içerik) okuyucuda açılıp çalışıyor', async () => {
  const k = kb('phet');
  if (!k) return ['ATLANDI', 'PhET paketi kurulu değil'];
  await git('/uygulama/index.html#kutuphane');
  const once = konsol.length;
  await okuyucudaAc(k, 'C/acid-base-solutions_tr.html');
  const s = await kadar(`document.readyState==='complete' && document.querySelector('canvas,#sim,.sim') && JSON.stringify({baslik:document.title,tuval:document.querySelectorAll('canvas').length,dugum:document.querySelectorAll('*').length,metin:(document.body.innerText||'').replace(/\\s+/g,' ').slice(0,60)})`, 25000, ic);
  await bekle(2500);
  await resim('U24-phet');
  const hatalar = konsol.slice(once);
  konsol.length = once; // simülasyonun kendi uyarıları genel "betik hatası yok" senaryosunu etkilemesin; burada ayrıca raporlanır
  return [!!s && JSON.parse(s).dugum > 50, s ? `${s}; simülasyon sırasında konsol hatası: ${hatalar.length ? hatalar.slice(0, 2).join(' || ').slice(0, 200) : 'yok'}` : `simülasyon çizilmedi; konsol: ${hatalar.slice(0, 2).join(' || ').slice(0, 300)}`];
});

await senaryo('U25', 'PDF dosyası: doğru türle ve yalıtımsız geliyor (tarayıcının PDF görüntüleyicisi açabilsin)', async () => {
  if (!VIKIKITAP) return ['ATLANDI', 'İçinde PDF olan Vikikitap kurulu değil'];
  const r = await fetch(`${TABAN}/zim/${encodeURIComponent(VIKIKITAP)}/C/_assets_/0c70a452f799bfe840676ee341124611/${encodeURIComponent('Vikiçocuk_Renkler.pdf')}`);
  const ilk = new TextDecoder().decode((await r.arrayBuffer()).slice(0, 5));
  const csp = r.headers.get('content-security-policy');
  return [r.status === 200 && /pdf/.test(r.headers.get('content-type')) && ilk === '%PDF-' && !csp, `yanıt ${r.status}, tür ${r.headers.get('content-type')}, başlangıç "${ilk}", yalıtım başlığı: ${csp ? 'VAR (Chrome PDF\'i açmaz)' : 'yok'} (görüntüleyicinin kendisi görünmez kipte denenemiyor)`];
});

await senaryo('U17', 'Kütüphane genel araması: adın ortasındaki kelimeyi buluyor ("peroksit" → Hidrojen peroksit)', async () => {
  await git('/uygulama/index.html#kutuphane');
  await kadar(`document.querySelectorAll('#kitaplar .kitap').length`);
  await ana(`(function(){var i=document.getElementById('ara');i.value='peroksit';i.dispatchEvent(new Event('input'))})()`);
  const r = await kadar(`document.querySelector('#ara-sonuc li,#ara-sonuc p') && document.getElementById('ara-sonuc').innerText.replace(/\\n+/g,' | ')`);
  return [/Hidrojen peroksit/.test(r || ''), `"peroksit" → ${(r || '').split(' | ').length} sonuç; "Hidrojen peroksit" listede: ${/Hidrojen peroksit/.test(r || '')}; ilk üçü: ${(r || '').split(' | ').slice(0, 3).join(' | ')}`];
});

await senaryo('U18', 'Telefon genişliğinde (375 px) sayfa yana taşmıyor', async () => {
  await gonder('Emulation.setDeviceMetricsOverride', { width: 375, height: 740, deviceScaleFactor: 2, mobile: true });
  const out = [];
  await git('/uygulama/index.html#kutuphane');
  await kadar(`document.querySelectorAll('#kitaplar .kitap').length`);
  out.push('Kütüphane ' + await ana(`document.documentElement.scrollWidth+'/'+innerWidth`));
  await ana(`document.querySelector('#kitaplar .kitap button').click()`);
  if (YENI) {
    await kadar(`document.querySelector('.kg-sayi b')`);
    await tikla('[data-kg-harf="A"]');
    await kadar(`document.querySelectorAll('#kg-liste-ic li').length>0`);
    out.push('Kitap girişi ' + await ana(`document.getElementById('kg-govde').scrollWidth+'/'+document.getElementById('kg-govde').clientWidth`));
    await resim('U18-telefon-kitap-girisi');
  }
  await git('/uygulama/index.html#simdi');
  out.push('Ana ekran ' + await ana(`document.documentElement.scrollWidth+'/'+innerWidth`));
  await resim('U18-telefon-ana');
  await gonder('Emulation.clearDeviceMetricsOverride');
  return [out.every(o => { const [a, b] = o.split(' ').pop().split('/').map(Number); return a <= b + 1; }), out.join('; ') + ' (içerik genişliği / ekran genişliği)'];
});

await senaryo('U19', 'Sesli rehber (kanama): adımlar, uyarılar ve seçenekler çalışıyor, bir dal sonuna kadar yürünüyor', async () => {
  await git('/uygulama/rehber.html?r=kanama');
  const ilk = await kadar(`document.querySelector('#kart h1') && document.querySelector('#kart h1').textContent`);
  const yol = [ilk];
  for (let i = 0; i < 12; i++) {
    const var_ = await ana(`(function(){var b=document.querySelector('.secim button');if(!b)return false;b.click();return true})()`);
    if (!var_) break;
    yol.push(await ana(`document.querySelector('#kart h1').textContent`));
  }
  const son = await ana(`/Rehberin sonu/.test(document.getElementById('kart').innerText)`);
  const tts = await ana(`'speechSynthesis' in window`);
  await resim('U19-rehber');
  return [yol.length >= 4 && son, `yol: ${yol.join(' → ')}; sona varıldı: ${son}; tarayıcıda ses motoru var: ${tts} (sesin kendisi duyularak doğrulanmadı)`];
});

await senaryo('U20', 'Tema: Gündüz / Koyu / Gece (kırmızı) düğmeleri çalışıyor ve hatırlanıyor', async () => {
  await git('/uygulama/index.html#simdi');
  await tikla('#tema button[data-t="gece"]');
  const renk = await ana(`getComputedStyle(document.body).backgroundColor`);
  await git('/uygulama/index.html#simdi');
  const kalici = await ana(`document.documentElement.getAttribute('data-tema')`);
  await resim('U20-gece-temasi');
  await tikla('#tema button[data-t="gunduz"]');
  return [kalici === 'gece' && /rgb\(10, 0, 0\)/.test(renk), `gece arka planı ${renk}; yeniden açınca tema: ${kalici}`];
});

await senaryo('U21', 'Paketler sekmesi: dil seçimi, hazır seçimler ve paket listesi çiziliyor', async () => {
  await git('/uygulama/index.html#paketler');
  const n = await kadar(`document.querySelectorAll('#paket-liste ul.paket li').length`);
  const mini = await ana(`document.getElementById('pf-mini').textContent`);
  await tikla('#dil-sec button[data-dil="tr,en"]');
  const n2 = await ana(`document.querySelectorAll('#paket-liste ul.paket li').length`);
  await tikla('#dil-sec button[data-dil="tr"]');
  return [n > 5 && n2 > n, `Türkçe: ${n} paket, Türkçe+İngilizce: ${n2} paket; Mini seçimi: "${mini}"`];
});

await senaryo('U22', 'Sayfalarda betik hatası yok', async () => [konsol.length === 0, konsol.length ? konsol.slice(0, 4).join(' || ') : 'tarayıcı konsolunda hata yok']);

const TM = DURUM.tam_metin;
await senaryo('U28', 'Kütüphane araması: "adında geçenler" ve "yazısının içinde geçenler" ayrı ayrı; özette kelime vurgulu; tıklayınca madde açılıyor', async () => {
  if (!TM) return [false, 'bu sürümde tam metin arama yok'];
  await git('/uygulama/index.html#kutuphane');
  await kadar(`document.querySelectorAll('#kitaplar .kitap').length`);
  await ana(`(function(){var i=document.getElementById('ara');i.value='kanama durdur';document.getElementById('ara-btn').click()})()`);
  const n = await kadar(`document.querySelectorAll('#ara-metin ul.sonuc li').length`, 15000);
  if (!n) return [false, 'yazısının içinde geçen sonuç çıkmadı: ' + await ana(`document.getElementById('ara-sonuc').innerText.slice(0,200)`)];
  const b = await ana(`(function(){var l=document.querySelectorAll('#ara-metin ul.sonuc li');return {bas:[].map.call(document.querySelectorAll('#ara-sonuc h4'),function(h){return h.textContent}),vurgu:[].map.call(document.querySelectorAll('#ara-metin mark'),function(m){return m.textContent}).slice(0,5),ilk:l[0].querySelector('a').textContent,kitap:(l[0].querySelector('.alt')||{}).textContent||'',ozet:l[0].querySelector('.ozet').textContent.slice(0,80)}})()`);
  await resim('U28-tam-metin-arama');
  await tikla('#ara-metin ul.sonuc li a');
  const acildi = await kadar(`!document.getElementById('okuyucu').hidden`);
  const icerik = await kadar(`document.body && document.body.innerText.length > 200`, 8000, ic);
  await tikla('#ok-kapat');
  const tamam = b.bas.length === 2 && b.vurgu.length > 0 && b.vurgu.every(v => /^(kanam|durdur)/i.test(v)) && acildi && !!icerik;
  return [tamam, `bölümler: ${b.bas.join(' | ')}; ${n} sonuç; ilk: "${b.ilk}" ${b.kitap}; özet: "${b.ozet}…"; vurgulananlar: ${b.vurgu.join(', ')}; tıklayınca madde açıldı: ${!!acildi && !!icerik}`];
});

await senaryo('U29', 'Kitap girişinde arama: yazısında geçenler de geliyor; "daha fazla göster" listeyi uzatıyor', async () => {
  if (!TM) return [false, 'bu sürümde tam metin arama yok'];
  await git('/uygulama/index.html#kutuphane');
  await kadar(`${kitapDugme(BUYUK)}`);
  await ana(`${kitapDugme(BUYUK)}.click()`);
  await kadar(`!!document.getElementById('kg-ara')`);
  await ana(`(function(){var i=document.getElementById('kg-ara');i.value='peroksit';i.dispatchEvent(new Event('input'))})()`);
  const n1 = await kadar(`document.querySelectorAll('#kg-metin ul.sonuc li').length`, 15000);
  const ad1 = await ana(`document.querySelectorAll('#kg-sonuc > ul.sonuc li').length`);
  await ana(`(function(){var i=document.getElementById('kg-ara');i.value='savaş';i.dispatchEvent(new Event('input'))})()`);
  const yirmi = await kadar(`document.querySelectorAll('#kg-metin ul.sonuc li').length===20&&!!document.querySelector('#kg-metin .metin-alt button')`, 15000);
  await resim('U29-kitapta-tam-metin');
  await tikla('#kg-metin .metin-alt button');
  const kirk = await kadar(`document.querySelectorAll('#kg-metin ul.sonuc li').length===40`, 15000);
  const tekil = await ana(`(function(){var a=[].map.call(document.querySelectorAll('#kg-metin ul.sonuc li a'),function(x){return x.dataset.yol});return new Set(a).size===a.length})()`);
  await tikla('#kg-kapat');
  return [n1 > ad1 && !!yirmi && !!kirk && tekil, `"peroksit": adında ${ad1}, yazısında ${n1} madde; "savaş": ilk 20, düğmeye basınca 40: ${!!kirk}, yinelenen yok: ${tekil}`];
});

await senaryo('U30', 'Ayarlar → Tam metin arama: kaç kitabın dizininin hazır olduğu ve ne kadar yer tuttuğu yazıyor', async () => {
  if (!TM) return [false, 'bu sürümde tam metin arama yok'];
  await git('/uygulama/index.html#ayarlar');
  const yazi = await kadar(`(function(){var t=document.getElementById('tm-bilgi').textContent;return t.indexOf('hazır')>0?t:false})()`);
  const dugme = await ana(`document.getElementById('tm-ac').textContent+' | '+document.getElementById('tm-sil').textContent`);
  await resim('U30-ayarlar-tam-metin');
  return [!!yazi && /^Açık/.test(yazi) && /kapat/.test(dugme), `"${String(yazi).slice(0, 160)}"; düğmeler: ${dugme}`];
});

// ---- Okuyucu özellikleri: sayfada bul, aranan kelimenin işaretlenmesi, içindekiler, sesli okuma ----
const KIMYA = kb('chemistry_nopic') || VIKIKITAP || BUYUK;
async function maddeAc(kitap, sorgu, yazidan) { // kitap girişinden arayıp ilk sonucu açar (yazidan: "yazısının içinde geçenler"den)
  await git('/uygulama/index.html#kutuphane');
  if (!await kadar(`!!${kitapDugme(kitap)}`)) return false;
  await ana(`${kitapDugme(kitap)}.click()`);
  await kadar(`!!document.getElementById('kg-ara')`);
  await ana(`(function(){var i=document.getElementById('kg-ara');i.value=${JSON.stringify(sorgu)};i.dispatchEvent(new Event('input'))})()`);
  const sec = yazidan ? '#kg-metin ul.sonuc li a' : '#kg-sonuc > ul.sonuc li a';
  if (!await kadar(`!!document.querySelector(${JSON.stringify(sec)})`, 15000)) return false;
  await tikla(sec);
  const hazir = await kadar(`document.readyState!=='loading' && document.body && document.body.innerText.length>200 && window.__imece===1`, 10000, ic);
  await bekle(300); // sayfanın "açıldım" iletisi arayüze ulaşsın
  return hazir;
}
const BUL_SAY = `(function(){var m=/^(\\d+) \\/ (\\d+)/.exec(document.getElementById('ok-bul-say').textContent);return m&&{sira:+m[1],adet:+m[2]}})()`;
// Çerçevenin içinde, uygulamanın kodundan bağımsız sadeleştirme ve sayım.
const SADE = `function(s){return s.replace(/I/g,'ı').toLocaleLowerCase('tr').replace(/ı/g,'i').replace(/ö/g,'o').replace(/ü/g,'u').replace(/ş/g,'s').replace(/ç/g,'c').replace(/ğ/g,'g')}`;
const okuyucuVar = await ana(`!!document.getElementById('ok-bul')`);

await senaryo('U31', 'Sayfada bul: kelime işaretleniyor, sayı doğru, Türkçe harfe takılmıyor, Sonraki/Önceki geziyor, kapatınca sayfa eski hâline dönüyor', async () => {
  if (!okuyucuVar) return [false, 'okuyucuda "Bul" düğmesi yok'];
  if (!await maddeAc(KIMYA, 'hidrojen')) return [false, 'madde açılamadı'];
  const once = await ic(`document.body.textContent.length`);
  await ana(`document.dispatchEvent(new KeyboardEvent('keydown',{key:'f',ctrlKey:true,bubbles:true,cancelable:true}))`); // Ctrl+F
  const acildi = await ana(`!document.getElementById('ok-bul-cubuk').hidden`);
  await ana(`(function(){var i=document.getElementById('ok-bul-q');i.value='HIDROJEN';i.dispatchEvent(new Event('input'))})()`);
  const say = await kadar(BUL_SAY, 8000);
  if (!say) return [false, 'sayı gelmedi: "' + await ana(`document.getElementById('ok-bul-say').textContent`) + '"'];
  const OLC = `(function(){var f=${SADE};var w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT),n,top=0;
    while(n=w.nextNode()){if(/^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|TEXTAREA)$/.test(n.parentNode.tagName))continue;var t=f(n.nodeValue),p=-1;while((p=t.indexOf('hidrojen',p+1))>=0)top++}
    var ms=[].slice.call(document.querySelectorAll('mark.imece-bul')),s=document.querySelector('mark.imece-simdi'),r=s&&s.getBoundingClientRect();
    return {bagimsiz:top,isaret:ms.length,hepsi:ms.every(function(m){return f(m.textContent)==='hidrojen'}),yazim:Array.from(new Set(ms.map(function(m){return m.textContent}))).slice(0,4),simdi:ms.indexOf(s),gorunur:!!r&&r.top>=0&&r.bottom<=innerHeight}})()`;
  const a = await ic(OLC);
  await resim('U31-sayfada-bul');
  await tikla('#ok-bul-sonra');
  const iki = await kadar(`/^2 \\//.test(document.getElementById('ok-bul-say').textContent)`, 3000);
  const b = await ic(OLC);
  await tikla('#ok-bul-once'); await tikla('#ok-bul-once');
  const sona = await kadar(`document.getElementById('ok-bul-say').textContent.indexOf('${say.adet} / ${say.adet}')===0`, 3000);
  await tikla('#ok-bul-kapat');
  const temiz = await kadar(`document.querySelectorAll('mark.imece-bul').length===0&&document.body.textContent.length===${once}`, 3000, ic);
  const tamam = acildi && say.sira === 1 && a.isaret === say.adet && a.bagimsiz === say.adet && a.hepsi && a.simdi === 0 && a.gorunur && !!iki && b.simdi === 1 && b.gorunur && !!sona && !!temiz;
  return [tamam, `Ctrl+F çubuğu açtı: ${acildi}; "HIDROJEN" → ${say.adet} yer (sayfayı bağımsız sayınca ${a.bagimsiz}, işaretlenen ${a.isaret}); yazımlar: ${a.yazim.join(', ')}; ilk işaret ekranda: ${a.gorunur}; Sonraki → 2. işaret ekranda: ${b.simdi === 1 && b.gorunur}; baştan Önceki → sonuncuya döndü: ${!!sona}; kapatınca işaretler kalktı ve yazı aynı: ${!!temiz}`];
});

await senaryo('U32', 'Arama sonucundan açılan maddede aranan kelimeler işaretli geliyor; ilk geçtiği yer ekranda', async () => {
  if (!okuyucuVar) return [false, 'okuyucuda "Bul" düğmesi yok'];
  if (!await maddeAc(KIMYA, 'hidrojen peroksit', true)) return [false, 'yazısında geçenlerden madde açılamadı'];
  const say = await kadar(BUL_SAY, 8000);
  const kutu = await ana(`document.getElementById('ok-bul-q').value`);
  const a = await ic(`(function(){var f=${SADE};var ms=[].slice.call(document.querySelectorAll('mark.imece-bul')),s=document.querySelector('mark.imece-simdi'),r=s&&s.getBoundingClientRect();
    return {isaret:ms.length,hepsi:ms.every(function(m){var t=f(m.textContent);return t.indexOf('hidrojen')===0||t.indexOf('peroksit')===0}),ornek:Array.from(new Set(ms.map(function(m){return m.textContent}))).slice(0,6),gorunur:!!r&&r.top>=0&&r.bottom<=innerHeight,baslik:document.title}})()`);
  await resim('U32-sonuctan-isaretli');
  await tikla('#ok-kapat');
  const tamam = !!say && a.isaret === say.adet && a.isaret >= 2 && a.hepsi && a.gorunur && kutu === 'hidrojen peroksit';
  return [tamam, `"hidrojen peroksit" araması → "${a.baslik}" açıldı; bul kutusunda: "${kutu}"; ${a.isaret} işaret (${a.ornek.join(', ')}); hepsi aranan kelimelerden: ${a.hepsi}; ilk işaret ekranda: ${a.gorunur}`];
});

await senaryo('U33', 'İçindekiler: sayfanın bölümleri listeleniyor; basınca o bölüme gidiyor; bölümü olmayan sayfada düğme kapalı', async () => {
  if (!okuyucuVar) return [false, 'okuyucuda "İçindekiler" düğmesi yok'];
  if (!await maddeAc(KIMYA, 'hidrojen')) return [false, 'madde açılamadı'];
  const acik = await kadar(`!document.getElementById('ok-icindekiler').disabled`, 5000);
  await tikla('#ok-icindekiler');
  const liste = await ana(`[].map.call(document.querySelectorAll('#ok-ic-liste li a'),function(a){return a.textContent})`);
  const sayfada = await ic(`[].map.call(document.querySelectorAll('h2,h3,h4'),function(h){return h.textContent.replace(/\\s+/g,' ').trim()}).filter(Boolean)`);
  await resim('U33-icindekiler');
  const hedef = Math.min(liste.length - 1, 2);
  await ana(`document.querySelectorAll('#ok-ic-liste li a')[${hedef}].click()`);
  const gitti = await kadar(`(function(){var h=[].filter.call(document.querySelectorAll('h2,h3,h4'),function(h){return h.textContent.trim()})[${hedef}],r=h.getBoundingClientRect();return scrollY>50&&r.top>-10&&r.top<200&&{ust:Math.round(r.top)}})()`, 4000, ic);
  const kapandi = await ana(`document.getElementById('ok-ic-panel').hidden`);
  await maddeAc(BUYUK, 'dunya savasi'); await bekle(700);
  const kapali = await ana(`document.getElementById('ok-icindekiler').disabled`);
  const bolum2 = await ic(`[].filter.call(document.querySelectorAll('h2,h3,h4'),function(h){return h.textContent.trim()}).length`);
  await tikla('#ok-kapat');
  const tamam = !!acik && liste.length >= 3 && JSON.stringify(liste) === JSON.stringify(sayfada) && !!gitti && kapandi && kapali === (bolum2 === 0);
  return [tamam, `${liste.length} bölüm (sayfadaki başlıklarla aynı: ${JSON.stringify(liste) === JSON.stringify(sayfada)}): ${liste.slice(0, 5).join(' · ')}…; "${liste[hedef]}" seçilince sayfa o başlığa kaydı: ${!!gitti}, panel kapandı: ${kapandi}; özet paketteki madde: ${bolum2} bölüm, düğme kapalı: ${kapali}`];
});

await senaryo('U34', 'Sesli okuma: paragraflar sırayla okunuyor, okunan paragraf işaretleniyor; duraklat, sonraki paragraf, bitir çalışıyor; Türkçe ses yoksa söylüyor (ses motoru taklit edildi, ses duyulmadı)', async () => {
  if (!(await ana(`!!document.getElementById('ok-ses')`))) return [false, 'okuyucuda "Sesli oku" düğmesi yok'];
  if (!await maddeAc(KIMYA, 'hidrojen')) return [false, 'madde açılamadı'];
  // Görünmez tarayıcıda ses yok: konuşma motoru, söylenenleri kaydeden bir taklitle değiştirilir.
  await ana(`(function(){window.__k=[];window.__sesler=[{lang:'tr-TR',name:'Deneme sesi',localService:true}];var s=window.speechSynthesis;
    s.getVoices=function(){return window.__sesler};s.cancel=function(){};
    s.speak=function(u){window.__k.push({t:u.text,dil:u.lang,hiz:u.rate});setTimeout(function(){if(u.onend)u.onend({})},25)}})()`);
  await tikla('#ok-ses');
  const basladi = await kadar(`window.__k.length>=6`, 8000);
  if (!basladi) return [false, 'okuma başlamadı: "' + await ana(`document.getElementById('ok-ses-durum').textContent`) + '"'];
  const durum = await ana(`document.getElementById('ok-ses-durum').textContent`);
  const k = await ana(`window.__k.slice(0,6)`);
  const c = await ic(`(function(){var o=document.querySelectorAll('.imece-okunan');return {adet:o.length,etiket:o[0]&&o[0].tagName,yazi:document.body.innerText.replace(/\\s+/g,' ')}})()`);
  await resim('U34-sesli-okuma');
  const sayfadan = k.filter(x => c.yazi.includes(x.t.replace(/\s+/g, ' ').slice(0, 25))).length;
  const dipnotsuz = k.every(x => !/\[\d+\]/.test(x.t)) && k.every(x => x.t.length <= 240);
  await tikla('#ok-ses-dur');
  await bekle(300); const n1 = await ana(`window.__k.length`); await bekle(500); const n2 = await ana(`window.__k.length`);
  const dugme = await ana(`document.getElementById('ok-ses-dur').textContent`);
  const ileri = await ana(`(function(){var d=document.getElementById('ok-ses-durum'),a=+/(\\d+) \\//.exec(d.textContent)[1];document.getElementById('ok-ses-ileri').click();return [a,+/(\\d+) \\//.exec(d.textContent)[1],d.textContent]})()`);
  const surdu = await kadar(`window.__k.length>${n2}`, 3000);
  await tikla('#ok-ses-kapat');
  await bekle(300);
  const n3 = await ana(`window.__k.length`); await bekle(400);
  const bitti = await ana(`document.getElementById('ok-ses-cubuk').hidden&&window.__k.length===${n3}`) && (await ic(`document.querySelectorAll('.imece-okunan').length`)) === 0;
  // Cihazda yalnızca İngilizce ses ve tarayıcının internet üzerinden çalışan Türkçe sesi varken: ikisi de kullanılmamalı.
  await ana(`window.__sesler=[{lang:'en-US',name:'English',localService:true},{lang:'tr-TR',name:'İnternet sesi',localService:false}];window.__k=[]`);
  await tikla('#ok-ses');
  const uyari = await kadar(`/Türkçe ses yüklü değil/.test(document.getElementById('ok-ses-durum').textContent)&&document.getElementById('ok-ses-durum').textContent`, 4000);
  const sessiz = await ana(`window.__k.length`);
  await tikla('#ok-ses-kapat'); await tikla('#ok-kapat');
  const tamam = /Okunuyor: \d+ \/ \d+ paragraf/.test(durum) && k.every(x => x.dil === 'tr-TR') && sayfadan >= 5 && dipnotsuz && c.adet === 1
    && n1 === n2 && /Sürdür/.test(dugme) && ileri[1] === ileri[0] + 1 && !!surdu && bitti && !!uyari && sessiz === 0;
  return [tamam, `durum: "${durum}"; ilk okunan: "${k[0].t.slice(0, 60)}…" (dil ${k[0].dil}); okunan 6 parçanın ${sayfadan} tanesi sayfanın yazısında bulundu, dipnot numarası yok ve hiçbiri 240 harften uzun değil: ${dipnotsuz}; işaretli paragraf: ${c.adet} (${c.etiket}); duraklatınca durdu: ${n1 === n2} ("${dugme}"); sonraki paragraf: ${ileri[0]} → ${ileri[1]}; bitirince sustu ve işaret kalktı: ${bitti}; cihazda yalnızca İngilizce ses ve internet üzerinden çalışan Türkçe ses varken: "${String(uyari).slice(0, 70)}…", okunan: ${sessiz}`];
});

// ---- 0.16: rehberlerin kaynak ve onay durumu ----
await senaryo('U44', 'Rehberler: her bölümün başında durumu yazıyor; kaynaklı bölümlerde kutular kaynağa bağlı ve altta kaynak listesi var; onay metnin özetine bağlı', async () => {
  if (!(await ana(`typeof window.imeceRehberDenetle==='function'&&!!window.REHBER_KAYNAK`))) return [false, 'bu sürümde rehberlerin kaynak/onay durumu yok (hepsi tek bir "taslak" uyarısıyla duruyor)'];
  await git('/uygulama/index.html#su');
  const b = await ana(`(function(){var out={};Object.keys(REHBER_KAYNAK.bolumler).forEach(function(id){var s=document.getElementById(id),v=REHBER_KAYNAK.bolumler[id];if(!s)return;
    var d=s.querySelector('.rehber-durum');out[id]={durum:v.durum,sinif:d?d.className.replace('rehber-durum ',''):'YOK',baslik:d?d.querySelector('b').textContent:'',
      kaynak:(v.kaynaklar||[]).length,liste:s.querySelectorAll('.kaynakca li').length,isaret:s.querySelectorAll('.kn').length,
      kartlar:[].filter.call(s.querySelectorAll('.kart'),function(k){return !k.classList.contains('kaynakca')&&!k.querySelector('[data-ilgili]')&&!k.querySelector('.kn')&&!k.hasAttribute('data-kaynaksiz')}).length}});return out})()`);
  await resim('U44-rehber-kaynaklar');
  const adlar = Object.keys(b), kaynakli = adlar.filter(a => b[a].durum === 'kaynakli'), taslak = adlar.filter(a => b[a].durum !== 'kaynakli');
  const uyumsuz = adlar.filter(a => b[a].sinif !== (b[a].durum === 'kaynakli' ? 'kaynakli' : 'taslak') || b[a].liste !== b[a].kaynak || (b[a].durum === 'kaynakli' && (b[a].kaynak === 0 || b[a].isaret === 0 || b[a].kartlar > 0)));
  // SHA-256: bilinen değer ve Node'un hesabıyla karşılaştır
  const { createHash } = await import('node:crypto');
  const metin = 'Türkçe deneme: ğüşıöç İĞÜŞÖÇ — ' + 'x'.repeat(1000);
  const s1 = await ana(`window.imeceSha256('abc')`), s2 = await ana(`window.imeceSha256(${JSON.stringify(metin)})`);
  const shaTamam = s1 === 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad' && s2 === createHash('sha256').update(metin, 'utf8').digest('hex');
  // Onay denetimi: sayfanın kendi kaynağından bir bölümün özeti; doğru özetle "geçerli", yanlış özetle "geçersiz"
  const sayfa = await (await fetch(TABAN + '/uygulama/index.html')).text();
  const m = /<!--rehber:su-->([\s\S]*?)<!--\/rehber:su-->/.exec(sayfa);
  const dogru = createHash('sha256').update(m[1], 'utf8').digest('hex');
  const d = await ana(`(function(){return fetch('/uygulama/index.html',{cache:'no-store'}).then(function(r){return r.text()}).then(function(t){
    return window.imeceRehberDenetle({bolumler:{su:{onay:{ozet:${JSON.stringify(dogru)}}},deprem:{onay:{ozet:'${'0'.repeat(64)}'}},gida:{}}},t)})})()`);
  // Sesli rehber sayfası
  // gözden geçirme tarihi bir yılı aşınca bölüm bunu söylemeli; bugün söylememeli
  const eski = await ana(`(function(){var bugun=document.querySelectorAll('.rehber-eski').length;
    window.imeceSimdi=Date.parse('2028-01-15T00:00:00Z');window.imeceRehberCiz();var sonra=document.querySelectorAll('.rehber-eski').length;
    window.imeceSimdi=undefined;window.imeceRehberCiz();
    return {bugun:bugun,sonra:sonra,geri:document.querySelectorAll('.rehber-eski').length,
      sinir:[window.imeceRehberEski('2026-11-18',Date.parse('2027-11-18T00:00:00Z')),window.imeceRehberEski('2026-11-18',Date.parse('2027-11-21T00:00:00Z'))]}})()`);
  const eskiTamam = eski.bugun === 0 && eski.sonra === adlar.length && eski.geri === 0 && eski.sinir[0] === false && eski.sinir[1] === true;
  await git('/uygulama/rehber.html?r=kanama');
  const kanama = await kadar(`(function(){var k=document.getElementById('kaynak');return k&&k.textContent.length>20&&k.textContent})()`, 6000);
  const kanamaDurum = /KAYNAKLI|TASLAK|ONAYLI/.exec(String(kanama));
  // sesli rehberde her adımın altında kaynak numaraları yazmalı ve bu numaralar sayfanın altındaki listede bulunmalı
  const dugum = await ana(`(function(){var k=document.getElementById('dugum-kn'),l=[].map.call(document.querySelectorAll('#kaynak ol li'),function(x){return +x.value});
    var n=k?(k.textContent.match(/\\[(\\d+)\\]/g)||[]).map(function(x){return +x.slice(1,-1)}):[];return {n:n,eksik:n.filter(function(x){return l.indexOf(x)<0}),liste:l.length}})()`);
  const dugumTamam = dugum.n.length > 0 && dugum.eksik.length === 0;
  await git('/uygulama/index.html#simdi');  // sonraki senaryolar ana sayfada başlar
  const tamam = adlar.length >= 9 && uyumsuz.length === 0 && shaTamam && d.su.onay === 'gecerli' && d.su.ozet === dogru && d.deprem.onay === 'gecersiz' && d.gida.onay === 'yok' && !!kanamaDurum && dugumTamam && eskiTamam;
  return [tamam, `${adlar.length} bölüm: kaynaklı ${kaynakli.length} (${kaynakli.join(', ') || '-'}), taslak ${taslak.length} (${taslak.join(', ') || '-'}); durum yazısı, kaynak listesi ya da kutu–kaynak bağı uymayan: ${uyumsuz.join(', ') || 'yok'}; özet hesabı (SHA-256) bilinen değerle ve Node'la aynı: ${shaTamam}; doğru özetli onay: ${d.su.onay}, yanlış özetli: ${d.deprem.onay}, onaysız: ${d.gida.onay}; "gözden geçirme gecikti" uyarısı bugün ${eski.bugun} bölümde, saat 2028'e alınınca ${eski.sonra} bölümde, geri alınınca ${eski.geri} bölümde (bir yıl sınırı: ${eski.sinir.join(' / ')}); sesli kanama rehberinde durum: ${kanamaDurum ? kanamaDurum[0] : 'YOK'}, ilk adımın kaynak numaraları: ${dugum.n.join(',') || 'YOK'} (listede ${dugum.liste} kaynak, listede olmayan: ${dugum.eksik.join(',') || 'yok'})`];
});

// ---- 0.17: verileri başka bir diske taşıma (yol yazmadan) ----
await senaryo('U45', 'Ayarlar → Kitapların durduğu yer: klasör yolu yazılan kutu yok, disk listeden seçiliyor; taşıma onay soruyor ve vazgeçince hiçbir şey başlamıyor; disk takılı değilken uyarı çıkıyor', async () => {
  await git('/uygulama/index.html#ayarlar');
  if (!(await ana(`!!document.getElementById('veri-tasi')`))) return [false, 'bu sürümde veri klasörü hâlâ yol yazılarak değişiyor (kural 7)'];
  const bilgi = await kadar(`(function(){var b=document.getElementById('veri-bilgi');return b&&b.textContent.length>10&&document.getElementById('veri-disk').options.length>0&&b.textContent})()`, 8000);
  const k = await ana(`(function(){var c=document.getElementById('veri-kart');return {yazi:c.querySelectorAll('input[type=text],input:not([type]),textarea').length,eskiKutu:!!document.getElementById('veri-yol'),
    diskler:[].map.call(document.getElementById('veri-disk').options,function(o){return o.value}),geriGizli:document.getElementById('veri-geri').hidden,tasiKapali:document.getElementById('veri-tasi').disabled}})()`);
  const suruculer = await (await fetch(TABAN + '/api/suruculer')).json();
  // Taşı düğmesi: onay sorusu çıkmalı; "vazgeç" denince sunucuda taşıma başlamamalı
  await ana(`(function(){window.__soru=null;window.__eskiConfirm=window.confirm;window.confirm=function(s){window.__soru=s;return false};document.getElementById('veri-tasi').click()})()`);
  const soru = await ana(`window.__soru`);
  await ana(`window.confirm=window.__eskiConfirm`);
  const durum = await (await fetch(TABAN + '/api/durum')).json();
  const tasima = await (await fetch(TABAN + '/api/veri-tasi')).json();
  // Disk takılı değilken (sunucunun böyle bir durum bildirdiği varsayılarak) kart ve kütüphane uyarısı
  const yok = await ana(`(function(){window.imeceVeriCiz({yerel:true,veri:'x',veri_yok:true,veri_yok_yol:'Q:\\\\Imece-veri',veri_varsayilan:false,zim_sayisi:0,bos_mb:1});
    var r={kart:document.getElementById('veri-bilgi').textContent,uyari:document.getElementById('veri-yok-uyari').textContent,kapali:document.getElementById('veri-tasi').disabled&&document.getElementById('veri-disk').disabled,geriGizli:document.getElementById('veri-geri').hidden};
    return r})()`);
  await resim('U45-veri-yeri');
  // gerçek duruma geri çiz
  await ana(`fetch('/api/durum').then(function(r){return r.json()}).then(window.imeceVeriCiz)`);
  const geri = await kadar(`document.getElementById('veri-yok-uyari').textContent===''&&!document.getElementById('veri-tasi').disabled`, 5000);
  const tamam = !!bilgi && /İmece klasörünün içinde/.test(String(bilgi)) && k.yazi === 0 && !k.eskiKutu && k.diskler.length === suruculer.length && k.diskler.every((d, i) => d === suruculer[i].yol)
    && k.geriGizli && !k.tasiKapali && /taşınsın mı/.test(String(soru)) && /sağlam/.test(String(soru)) && durum.veri_varsayilan === true && tasima.aktif === false
    && /Disk takılı değil/.test(yok.kart) && /disk takılı değil/i.test(yok.uyari) && /silinmedi/.test(yok.uyari) && yok.kapali && yok.geriGizli && !!geri;
  return [tamam, `kartta: "${String(bilgi).slice(0, 70)}"; yazı kutusu sayısı: ${k.yazi} (eski yol kutusu: ${k.eskiKutu}); listede ${k.diskler.length} disk (sunucunun bildirdiğiyle aynı: ${k.diskler.every((d, i) => suruculer[i] && d === suruculer[i].yol)}); "geri al" düğmesi gizli: ${k.geriGizli}; taşıya basınca soru: "${String(soru).slice(0, 60)}…"; vazgeçince taşıma başlamadı: ${tasima.aktif === false && durum.veri_varsayilan === true}; disk yokken kart: "${yok.kart.slice(0, 50)}", kütüphane uyarısı: "${yok.uyari.slice(0, 60)}…", düğmeler kapalı: ${yok.kapali}; gerçek duruma dönünce uyarı kalktı: ${!!geri}. Gerçek taşıma arayüzden yapılmadı (asıl kütüphaneyi taşırdı); sunucu senaryoları Y3–Y5 ayrı bir kopyada sınadı.`];
});

// ---- 0.19: sekmeler kaydırmasız, seçim dökümü, sanat galerisi, oyunlar ----
await senaryo('U47', 'Sekmelerde yatay kaydırma yok, "şebekesiz çalışır" damgası yok; hazır seçimlerin içeriği listeleniyor; Sanat galerisi eseri künyesiyle büyütüyor; Oyunlar (satranç, sudoku, mangala) oynanıyor', async () => {
  await git('/uygulama/index.html#paketler');
  if (!(await ana(`!!document.getElementById('oyun-sec')`))) return [false, 'bu sürümde Sanat ve Oyunlar bölümleri yok'];
  const nav = await ana(`(function(){var n=document.getElementById('sekmeler'),ust=[].map.call(n.querySelectorAll('button'),function(b){return b.offsetTop});
    return {tasma:n.scrollWidth-n.clientWidth,kay:getComputedStyle(n).overflowX,satir:ust.filter(function(v,i){return ust.indexOf(v)===i}).length,sekme:ust.length,damga:!!document.querySelector('.damga'),sayfa:document.documentElement.scrollWidth-document.documentElement.clientWidth}})()`);
  const dokum = await kadar(`(function(){var d=document.querySelectorAll('#profil-icerik details');if(d.length!==3)return false;return [].map.call(d,function(x){return {ozet:x.querySelector('summary').textContent,adet:x.querySelectorAll('li').length}})})()`, 8000);
  const kat = await (await fetch(TABAN + '/uygulama/katalog.json')).json();
  const beklenen = ['mini', 'standart', 'tam'].map(p => kat.icerikler.filter(x => x.profiller.includes(p) && (x.dil === 'tr' || x.dil === '-' || !x.dil)).length);
  // Sanat
  await ana(`document.querySelector('#sekmeler button[data-id="sanat"]').click()`);
  const gal = await kadar(`(function(){var l=document.getElementById('sanat-liste');if(!l.textContent)return false;return {galeri:l.querySelectorAll('.sanat-grid').length,kare:l.querySelectorAll('.sanat-kare').length,bos:/Henüz eser yok/.test(l.textContent)}})()`, 8000);
  let eser = null;
  if (gal && gal.kare) {
    await ana(`document.querySelector('.sanat-kare').click()`);
    eser = await kadar(`(function(){var b=document.getElementById('sanat-buyuk'),r=document.getElementById('sanat-resim');if(b.hidden||!r.complete||!r.naturalWidth)return false;return {en:r.naturalWidth,kunye:document.getElementById('sanat-kunye').innerText}})()`, 10000);
    await resim('U47-sanat');
    await ana(`document.getElementById('sanat-kapat').click()`);
  }
  // Oyunlar
  await ana(`document.querySelector('#sekmeler button[data-id="oyunlar"]').click()`);
  await ana(`document.querySelector('[data-oyun="satranc"]').click()`);
  const st = await ana(`(function(){var q=function(k){return document.querySelector('#st-tahta [data-k="'+k+'"]')};var kare=document.querySelectorAll('.st-kare').length;q(52).click();var hedef=document.querySelectorAll('.st-kare.hedef').length;q(36).click();
    var sonra=document.getElementById('st-durum').textContent,e4=q(36).textContent,e2=q(52).textContent;document.getElementById('st-geri').click();
    return {kare:kare,hedef:hedef,sonra:sonra,e4:e4,e2:e2,geri:document.getElementById('st-durum').textContent,perft:window.imeceSatranc.perft(window.imeceSatranc.fen(window.imeceSatranc.baslangic),3)}})()`);
  await resim('U47-satranc');
  await ana(`document.querySelector('[data-oyun="sudoku"]').click()`);
  const sd = await ana(`(function(){var k=document.querySelectorAll('.sd-kare'),verili=document.querySelectorAll('.sd-kare.verili').length,g=[].map.call(k,function(x){return +x.textContent||0});
    var bos=[].filter.call(k,function(x){return !x.classList.contains('verili')})[0];bos.click();document.querySelector('#sd-rakam [data-v="5"]').click();
    var yazildi=[].filter.call(document.querySelectorAll('.sd-kare'),function(x){return !x.classList.contains('verili')})[0].textContent;
    return {kare:k.length,verili:verili,tek:window.imeceSudoku.cozumSay(g,3),yazildi:yazildi}})()`);
  await ana(`document.querySelector('[data-oyun="mangala"]').click()`);
  const mg = await ana(`(function(){var say=function(){return [].reduce.call(document.querySelectorAll('.mg-kuyu,.mg-hazne'),function(a,x){return a+(+x.textContent)},0)};var once=say();
    document.querySelector('.mg-kuyu.oynar[data-i="3"]').click();var d=document.getElementById('mg-durum').textContent,h1=document.getElementById('mg-h1').textContent;return {once:once,sonra:say(),durum:d,hazne:h1}})()`);
  const tamam = nav.tasma <= 1 && nav.kay !== 'auto' && nav.kay !== 'scroll' && nav.satir >= 2 && !nav.damga && nav.sayfa <= 1
    && !!dokum && dokum.every((d, i) => d.adet === beklenen[i] && d.adet > 0) && !!gal && (gal.bos || (!!eser && eser.en >= 500 && /Public domain|CC0/i.test(eser.kunye) && /commons\.wikimedia\.org/.test(eser.kunye)))
    && st.kare === 64 && st.hedef === 2 && /Siyah/.test(st.sonra) && st.e4 === '♟' && st.e2 === '' && /Beyaz/.test(st.geri) && st.perft === 8902
    && sd.kare === 81 && sd.tek === 1 && sd.yazildi === '5' && mg.once === 48 && mg.sonra === 48 && mg.hazne === '1' && /yine oynuyor/.test(mg.durum);
  return [tamam, `sekmeler: ${nav.sekme} sekme ${nav.satir} satırda, yatay taşma ${nav.tasma} px (kaydırma: ${nav.kay}), sayfada yatay taşma ${nav.sayfa} px, damga var mı: ${nav.damga}; seçim dökümü: ${dokum ? dokum.map(d => d.ozet).join(' | ') : 'YOK'} (katalogdan beklenen: ${beklenen.join(', ')}); Sanat: ${gal ? (gal.bos ? 'galeri indirilmemiş (boş durum yazısı çıktı)' : `${gal.galeri} galeri, ${gal.kare} eser; büyütülen eser ${eser ? eser.en + ' px, künye: “' + eser.kunye.replace(/\n/g, ' / ').slice(0, 150) + '”' : 'AÇILMADI'}`) : 'YÜKLENMEDİ'}; satranç: ${st.kare} kare, e2 piyonunun ${st.hedef} hedefi, e4 sonrası “${st.sonra}”, geri alınca “${st.geri}”, 3 hamle derinliğinde ${st.perft} konum (bilinen değer 8902); sudoku: ${sd.kare} kare, ${sd.verili} verili, çözüm sayısı ${sd.tek}, yazılan rakam ${sd.yazildi}; mangala: taş ${mg.once} → ${mg.sonra}, 4. kuyudan sonra hazne ${mg.hazne}, “${mg.durum}”`];
});

// ---- 0.18: İngilizce arayüz (isteğe bağlı çeviri katmanı) ----
await senaryo('U46', 'İngilizce arayüz: EN seçilince bütün ana ekranlarda arayüz yazıları İngilizce, çevrilmemiş arayüz yazısı kalmıyor; rehberler Türkçe kalıyor ve nedenini söylüyor; TR seçilince her şey Türkçe', async () => {
  await git('/uygulama/index.html#simdi');
  if (!(await ana(`!!document.getElementById('arayuz-dil')`))) return [false, 'bu sürümde arayüz dili seçimi yok (yalnızca Türkçe)'];
  const trSekme = await ana(`[].map.call(document.querySelectorAll('#sekmeler button'),function(b){return b.textContent.replace(/^\\d+/,'').trim()})`);
  await ana(`document.querySelector('#arayuz-dil [data-dil="en"]').click()`);
  await bekle(1200);
  const en = await kadar(`window.imeceDil==='en'&&document.documentElement.lang==='en'`, 6000);
  // Türkçe kalmış arayüz yazılarını topla: Türkçe'ye özgü harf ya da sık geçen Türkçe kelime taşıyan, içerik olmayan yazı düğümleri
  const topla = `(function(){var R=(window.REHBER_KAYNAK||{}).bolumler||{},ATLA=window.IMECE_EN.atla,out={};
    var tr=/[çğıöşüÇĞİÖŞÜ]|(^|[^A-Za-z])(kitap|kitabın|madde|maddeler|sayfa|yok|dizin|hazır|ekle|geri|tam metin|ile|için|bir|ve|bu|daha|olan|sonra)([^A-Za-z]|$)/i;
    function gor(el){if(!el||el.closest('script,style,textarea,iframe,.dil-notu,[hidden]'))return false;if(ATLA&&el.closest(ATLA))return false;
      var s=el.closest('section');if(s&&!s.classList.contains('aktif'))return false;if(s&&R[s.id]&&!el.closest('h2'))return false;return true}
    var w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null),n;
    // Türkçe sayılmayanlar: özel adlar (İmece, Türkiye), bilerek iki dilli bırakılan dil düğmesi, örnek kelimeler, klasör yolları
    function ayikla(t){return t.replace(/İmece|İMC|Türkiye|Arayüz dili|kanama, deprem, ısırgan…?|“Yemek:Mercimek çorbası” → Yemek|[A-Z]:\\\\[^ ]*/g,'')}
    while((n=w.nextNode())){var t=n.nodeValue.replace(/\\s+/g,' ').trim();if(t.length>1&&tr.test(ayikla(t))&&gor(n.parentElement))out[t]=1}
    [].forEach.call(document.querySelectorAll('[placeholder],[title]'),function(el){['placeholder','title'].forEach(function(a){var t=el.getAttribute(a);if(t&&tr.test(ayikla(t))&&gor(el))out['@'+a+': '+t]=1})});
    return Object.keys(out)})()`;
  const kalan = {};
  const ekran = async (ad, hazirla) => { if (hazirla) await hazirla(); await bekle(900); for (const t of await ana(topla)) (kalan[t] = kalan[t] || []).push(ad); await resim('U46-en-' + ad); };
  const bolumler = ['simdi', 'ilkyardim', 'kutuphane', 'dizin', 'muzik', 'paketler', 'ayarlar'];
  for (const b of bolumler) await ekran(b, () => ana(`document.querySelector('#sekmeler button[data-id="${b}"]').click()`));
  // kitap giriş ekranı ve okuyucu çubuğu
  await ekran('kitap-girisi', async () => { await ana(`document.querySelector('#sekmeler button[data-id="kutuphane"]').click()`); await kadar(`!!${kitapDugme(VIKIKITAP)}`, 8000); await ana(`${kitapDugme(VIKIKITAP)}.click()`); await kadar(`!!document.getElementById('kg-denetle')||!!document.querySelector('[data-rastgele]')`, 8000); });
  await ekran('okuyucu', async () => { await ana(`(function(){var b=[].filter.call(document.querySelectorAll('button'),function(x){return /Random article/.test(x.textContent)})[0];if(b)b.click()})()`); await kadar(`!document.getElementById('okuyucu').hidden`, 8000); });
  const sekme = await ana(`[].map.call(document.querySelectorAll('#sekmeler button'),function(b){return b.textContent.replace(/^\\d+/,'').trim()})`);
  const not = await ana(`(function(){var R=window.REHBER_KAYNAK.bolumler,n=0,t=0;Object.keys(R).forEach(function(id){var s=document.getElementById(id);if(!s)return;t++;if(s.querySelector('.dil-notu'))n++});
    var su=document.getElementById('su');return {rehber:t,notlu:n,govdeTurkce:/Sıcak su tankı/.test(su.textContent),durum:/KAYNAKLI/.test(su.textContent),baslik:su.querySelector('h2').textContent}})()`);
  const soru = await ana(`(function(){var g=null,c=window.confirm;return window.imeceCevir('Bu sayfadaki not silinsin mi?')})()`);
  // Türkçeye dönüş
  await ana(`document.querySelector('#arayuz-dil [data-dil="tr"]').click()`);
  await bekle(1200);
  const trGeri = await kadar(`window.imeceDil==='tr'`, 6000);
  const trSekme2 = await ana(`[].map.call(document.querySelectorAll('#sekmeler button'),function(b){return b.textContent.replace(/^\\d+/,'').trim()})`);
  const ingKaldi = await ana(`/Library|Settings|Packages/.test(document.getElementById('sekmeler').textContent)||!!document.querySelector('.dil-notu')||document.documentElement.lang==='en'`);
  const liste = Object.keys(kalan);
  const tamam = !!en && liste.length === 0 && sekme.includes('Library') && sekme.includes('Settings') && sekme.includes('First aid') && not.rehber >= 9 && not.notlu === not.rehber && not.govdeTurkce && not.durum
    && /^Delete the note/.test(String(soru)) && !!trGeri && JSON.stringify(trSekme) === JSON.stringify(trSekme2) && !ingKaldi;
  return [tamam, `EN seçilince sekmeler: ${sekme.join(' | ')}; gezilen ekran: ${bolumler.length + 2} (${bolumler.join(', ')}, kitap girişi, okuyucu); Türkçe kalmış arayüz yazısı: ${liste.length}${liste.length ? ' → ' + liste.slice(0, 90).map(t => `“${t.slice(0, 90)}” [${kalan[t][0]}]`).join(' ; ') : ''}; rehber bölümlerinde “yalnızca Türkçe” notu: ${not.notlu}/${not.rehber}, rehber gövdesi Türkçe kaldı: ${not.govdeTurkce}, bölüm başlığı: “${not.baslik}”; onay sorusu çevirisi: “${soru}”; TR seçilince sekmeler eskisiyle aynı: ${JSON.stringify(trSekme) === JSON.stringify(trSekme2)}, İngilizce kalıntı: ${ingKaldi}. Kitapların kendi içeriği (adlar, açıklamalar, arama sonuçları) ve rehber metinleri çevrilmez; çevirinin doğruluğunu bir İngilizce konuşan okumadı.`];
});

// ---- 0.14: kare kod, sekmeler, notlar, İleri, tam ekran, katalog türleri, başka İmece'den kitap alma ----
const ag = async ac => (await fetch(TABAN + '/api/ag', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ac }) })).json();
async function anaJest(ifade) { // kullanıcı tıklaması sayılan çalıştırma (tam ekran gibi yalnızca tıklamayla izin verilen işler için)
  const r = await gonder('Runtime.evaluate', { expression: ifade, awaitPromise: true, returnByValue: true, userGesture: true });
  return r.result.value;
}
async function icSec(kosul) { // koşulu sağlayan çerçevenin içinde çalıştırıcı döner (birden çok sekme açıkken)
  for (let i = cerceveler.length - 1; i >= 0; i--) {
    const c = cerceveler[i];
    try {
      const r = await gonder('Runtime.evaluate', { expression: kosul, returnByValue: true, contextId: c.baglam }, c.oturum);
      if (r.result && r.result.value) return async ifade => (await gonder('Runtime.evaluate', { expression: ifade, awaitPromise: true, returnByValue: true, contextId: c.baglam }, c.oturum)).result.value;
    } catch { }
  }
  return null;
}
// Kare kodu uygulamanın üreticisinden bağımsız çözer: biçim bilgisi (iki kopya + BCH), maske, zikzak veri sırası,
// blokların Reed–Solomon sağlaması (belirtilerin hepsi sıfır olmalı) ve bayt kipindeki metin.
function kareCoz(svg) {
  const n = +/data-boyut="(\d+)"/.exec(svg)[1], M = Array.from({ length: n }, () => new Array(n).fill(0));
  for (const m of svg.matchAll(/M(\d+) (\d+)h1v1h-1z/g)) M[+m[2] - 4][+m[1] - 4] = 1;
  const v = (n - 17) / 4, T = { 1: [1, 16, 10, 0], 2: [1, 28, 16, 18], 3: [1, 44, 26, 22], 4: [2, 32, 18, 26], 5: [2, 43, 24, 30], 6: [4, 27, 16, 34] }[v];
  if (!T) return { hata: 'tanınmayan boyut ' + n };
  const g = (x, y) => M[y][x];
  let a = 0, b = 0;
  for (let i = 0; i <= 5; i++) a |= g(8, i) << i;
  a |= g(8, 7) << 6; a |= g(8, 8) << 7; a |= g(7, 8) << 8;
  for (let i = 9; i < 15; i++) a |= g(14 - i, 8) << i;
  for (let i = 0; i < 8; i++) b |= g(n - 1 - i, 8) << i;
  for (let i = 8; i < 15; i++) b |= g(8, n - 15 + i) << i;
  const ham = a ^ 0x5412;
  let kalan = ham; for (let i = 14; i >= 10; i--) if ((kalan >> i) & 1) kalan ^= 0x537 << (i - 10);
  const maske = (ham >> 10) & 7, duzey = ham >> 13;
  const sabit = (x, y) => (x < 9 && y < 9) || (x >= n - 8 && y < 9) || (x < 9 && y >= n - 8) || x === 6 || y === 6 || (T[3] && Math.abs(x - T[3]) <= 2 && Math.abs(y - T[3]) <= 2);
  const mf = [(x, y) => (x + y) % 2 === 0, (x, y) => y % 2 === 0, (x, y) => x % 3 === 0, (x, y) => (x + y) % 3 === 0, (x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0,
    (x, y) => (x * y) % 2 + (x * y) % 3 === 0, (x, y) => ((x * y) % 2 + (x * y) % 3) % 2 === 0, (x, y) => ((x + y) % 2 + (x * y) % 3) % 2 === 0][maske];
  const bitler = [];
  for (let sag = n - 1; sag >= 1; sag -= 2) {
    if (sag === 6) sag = 5;
    for (let dik = 0; dik < n; dik++) for (let j = 0; j < 2; j++) {
      const x = sag - j, y = ((sag + 1) & 2) === 0 ? n - 1 - dik : dik;
      if (!sabit(x, y)) bitler.push(g(x, y) ^ (mf(x, y) ? 1 : 0));
    }
  }
  const toplam = T[0] * (T[1] + T[2]), kod = [];
  for (let i = 0; i < toplam; i++) { let x = 0; for (let j = 0; j < 8; j++) x = x << 1 | bitler[i * 8 + j]; kod.push(x); }
  const blok = Array.from({ length: T[0] }, () => []); let k = 0;
  for (let i = 0; i < T[1]; i++) for (const bl of blok) bl.push(kod[k++]);
  for (let i = 0; i < T[2]; i++) for (const bl of blok) bl.push(kod[k++]);
  const us = [1]; for (let i = 1; i < 255; i++) { let x = us[i - 1] << 1; if (x & 256) x ^= 0x11D; us.push(x); }
  const lg = {}; us.forEach((x, i) => { lg[x] = i; });
  const carp = (p, q) => (p && q ? us[(lg[p] + lg[q]) % 255] : 0);
  let saglam = true;
  for (const bl of blok) for (let j = 0; j < T[2]; j++) {
    let s = 0; for (const c of bl) s = carp(s, us[j]) ^ c; // Horner: çokterimi α^j noktasında hesapla
    if (s !== 0) saglam = false;
  }
  const veri = [].concat(...blok.map(bl => bl.slice(0, T[1]))), vb = [];
  for (const x of veri) for (let j = 7; j >= 0; j--) vb.push((x >> j) & 1);
  const al = (bas, adet) => { let x = 0; for (let j = 0; j < adet; j++) x = x << 1 | vb[bas + j]; return x; };
  const kip = al(0, 4), uz = al(4, 8), bayt = [];
  for (let i = 0; i < uz; i++) bayt.push(al(12 + 8 * i, 8));
  return { metin: Buffer.from(bayt).toString('utf8'), surum: v, kip, duzey, maske, bicim: kalan === 0 && a === b, saglam };
}

await senaryo('U39', 'Kare kod: üretilen kareler bağımsız bir çözücüyle okunuyor (biçim bilgisi geçerli, hata düzeltme sağlaması tutuyor, metin aynı); paylaşım kartındaki kare adresi veriyor', async () => {
  if (!(await ana(`typeof window.imeceKareKodSvg==='function'`))) return [false, 'bu sürümde kare kod yok'];
  const metinler = ['a', 'x'.repeat(14), 'x'.repeat(15), 'http://192.168.1.8:8642', 'http://192.168.100.200:8642', 'y'.repeat(26), 'y'.repeat(27), 'z'.repeat(42), 'z'.repeat(43),
    'k'.repeat(62), 'k'.repeat(63), 'm'.repeat(84), 'm'.repeat(85), 'n'.repeat(106), 'Türkçe: ğüşıöç İĞÜŞÖÇ', '0123456789 !"#$%&()*+,-./:;<=>?@[]^_{|}~'];
  const kotu = [], surumler = new Set(), maskeler = new Set();
  for (const m of metinler) {
    const svg = await ana(`window.imeceKareKodSvg(${JSON.stringify(m)})`);
    const c = svg ? kareCoz(svg) : { hata: 'üretilmedi' };
    if (c.hata || c.metin !== m || !c.bicim || !c.saglam || c.kip !== 4 || c.duzey !== 0) kotu.push(`${m.slice(0, 12)}…(${Buffer.byteLength(m)} bayt): ${JSON.stringify(c).slice(0, 110)}`);
    else { surumler.add(c.surum); maskeler.add(c.maske); }
  }
  const sigmaz = await ana(`window.imeceKareKodSvg(${JSON.stringify('q'.repeat(107))})`);
  let kart = { hata: 'ağ yok' };
  const a = await ag(true);
  if (a.acik && a.adres) {
    await git('/uygulama/index.html#ayarlar');
    const svg = await kadar(`(function(){var s=document.querySelector('#ag-kare svg');return s&&s.outerHTML})()`, 6000);
    await resim('U39-kare-kod');
    kart = svg ? kareCoz(svg) : { hata: 'kartta kare yok' };
    kart.beklenen = a.adres;
    await ag(false);
  }
  const kartTamam = kart.hata === 'ağ yok' || (kart.metin === kart.beklenen && kart.bicim && kart.saglam);
  return [kotu.length === 0 && sigmaz === '' && surumler.size === 6 && kartTamam,
    `${metinler.length} metnin ${metinler.length - kotu.length} tanesi doğru çözüldü (1–106 bayt; sürümler ${[...surumler].sort().join(',')}; kullanılan maskeler ${[...maskeler].sort().join(',')}); çözülemeyen: ${kotu.length ? kotu.join(' || ') : 'yok'}; 107 baytlık metin için kare üretilmiyor: ${sigmaz === ''}; paylaşım kartındaki kare: ${kart.hata || `"${kart.metin}" (beklenen "${kart.beklenen}")`}. Telefon kamerasıyla okutulmadı.`];
});

await senaryo('U40', 'Sekmeler: "+ Sekme" yeni sekme açıyor; sekmeler birbirinden bağımsız geziliyor; Ctrl ile basılan bağlantı yeni sekmede açılıyor; sekme kapatılıyor', async () => {
  if (!(await ana(`!!document.getElementById('ok-yeni-sekme')`))) return [false, 'bu sürümde sekme yok'];
  if (!await maddeAc(KIMYA, 'hidrojen')) return [false, 'madde açılamadı'];
  const ilk = await ana(`document.getElementById('ok-baslik').textContent`);
  const serit0 = await ana(`document.getElementById('ok-sekmeler').hidden`);
  await tikla('#ok-yeni-sekme');
  await kadar(`document.querySelectorAll('#ok-sekmeler .ok-sekme').length===2`, 4000);
  await bekle(1200);
  const yeni = await icSec(`document.readyState==='complete'&&window.__imece===1&&document.title.length>0`);
  // yeni sekmede bir bağlantıya bas: yalnızca o sekme başka maddeye gitsin
  const hedef = await ic(`(function(){var a=[].filter.call(document.querySelectorAll('#mw-content-text p a[href]'),function(a){return a.getAttribute('href').charAt(0)!=='#'&&a.host===location.host})[0];if(!a)return '';a.click();return a.getAttribute('title')||a.textContent})()`);
  const ikinci = await kadar(`(function(){var t=document.getElementById('ok-baslik').textContent;return t!==${JSON.stringify(ilk)}&&t})()`, 8000);
  const adlar1 = await ana(`[].map.call(document.querySelectorAll('#ok-sekmeler [data-sekme]'),function(b){return b.title})`);
  await ana(`document.querySelector('#ok-sekmeler [data-sekme="0"]').click()`);
  const donus = await kadar(`document.getElementById('ok-baslik').textContent===${JSON.stringify(ilk)}`, 3000);
  const gorunen = await ana(`[].map.call(document.querySelectorAll('#ok-govde iframe'),function(f){return !f.hidden})`);
  const birinci = await icSec(`document.title===${JSON.stringify(ilk)}`);
  const ctrlHedef = birinci ? await birinci(`(function(){var a=[].filter.call(document.querySelectorAll('#mw-content-text p a[href]'),function(a){return a.getAttribute('href').charAt(0)!=='#'&&a.host===location.host})[1];if(!a)return '';a.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,ctrlKey:true}));return a.getAttribute('title')||a.textContent})()`) : '';
  const uc = await kadar(`document.querySelectorAll('#ok-sekmeler .ok-sekme').length===3`, 5000);
  const ucuncu = await kadar(`(function(){var t=document.getElementById('ok-baslik').textContent;return t&&t!==${JSON.stringify(ilk)}&&t!=='Yükleniyor…'&&t})()`, 8000);
  await resim('U40-sekmeler');
  const birinciDuruyor = birinci ? await birinci(`document.title`) : '';
  await ana(`document.querySelector('#ok-sekmeler [data-sekme-kapat="2"]').click()`);
  const iki = await kadar(`document.querySelectorAll('#ok-sekmeler .ok-sekme').length===2&&document.querySelectorAll('#ok-govde iframe').length===2`, 3000);
  await tikla('#ok-kapat');
  const kapandi = await ana(`document.getElementById('okuyucu').hidden&&document.querySelectorAll('#ok-govde iframe').length===1&&document.getElementById('ok-sekmeler').hidden`);
  const tamam = serit0 && !!yeni && !!ikinci && adlar1.length === 2 && adlar1[0] === ilk && adlar1[1] !== ilk && !!donus && JSON.stringify(gorunen) === '[true,false]' && !!uc && !!ucuncu && birinciDuruyor === ilk && !!iki && kapandi;
  return [tamam, `tek sekmeyken şerit gizli: ${serit0}; "+ Sekme" sonrası sekmeler: ${adlar1.join(' | ')} (ikincisinde "${hedef}" bağlantısına basıldı); birinci sekmeye dönünce başlık "${ilk}": ${!!donus}; Ctrl ile "${ctrlHedef}" → üçüncü sekme: "${ucuncu}", birinci sekme yerinde: ${birinciDuruyor === ilk}; sekme kapatınca 2 kaldı: ${!!iki}; okuyucuyu kapatınca tek boş sekme: ${kapandi}`];
});

await senaryo('U41', 'Not, İleri ve tam ekran: nota yazılan kaydediliyor, "Notlarım"da çıkıyor, yeniden açınca duruyor, siliniyor; Geri/İleri geziyor; tam ekran açılıp kapanıyor', async () => {
  if (!(await ana(`!!document.getElementById('ok-not')`))) return [false, 'bu sürümde not yok'];
  if (!await maddeAc(KIMYA, 'hidrojen')) return [false, 'madde açılamadı'];
  const ilk = await ana(`document.getElementById('ok-baslik').textContent`);
  const yazi = 'Deneme notu: suyun yarısı hidrojen. ' + Date.now();
  await tikla('#ok-not');
  await ana(`(function(){var t=document.getElementById('ok-not-metin');t.value=${JSON.stringify(yazi)};t.dispatchEvent(new Event('input'))})()`);
  const kayit = await kadar(`/^Kaydedildi/.test(document.getElementById('ok-not-durum').textContent)`, 5000);
  const dugme = await ana(`document.getElementById('ok-not').textContent`);
  // Geri / İleri
  const hedef = await ic(`(function(){var a=[].filter.call(document.querySelectorAll('#mw-content-text p a[href]'),function(a){return a.getAttribute('href').charAt(0)!=='#'&&a.host===location.host})[0];a.click();return 1})()`);
  const ikinci = await kadar(`(function(){var t=document.getElementById('ok-baslik').textContent;return t!==${JSON.stringify(ilk)}&&t})()`, 8000);
  const notBos = await ana(`document.getElementById('ok-not').textContent+'|'+document.getElementById('ok-not-panel').hidden`);
  await tikla('#ok-geri');
  const geri = await kadar(`document.getElementById('ok-baslik').textContent===${JSON.stringify(ilk)}`, 6000);
  await tikla('#ok-ileri');
  const ileri = await kadar(`document.getElementById('ok-baslik').textContent===${JSON.stringify(String(ikinci))}`, 6000);
  // Tam ekran
  await anaJest(`document.getElementById('ok-tam').click()`);
  const tam = await kadar(`document.fullscreenElement&&document.fullscreenElement.id==='okuyucu'&&document.getElementById('ok-tam').textContent`, 3000);
  await anaJest(`document.getElementById('ok-tam').click()`);
  const tamCik = await kadar(`!document.fullscreenElement&&document.getElementById('ok-tam').textContent==='Tam ekran'`, 3000);
  await tikla('#ok-kapat');
  await git('/uygulama/index.html#kutuphane');
  const liste = await kadar(`(function(){var l=[].map.call(document.querySelectorAll('#notlar .liste-li'),function(x){return x.innerText});return l.length&&l})()`, 5000);
  const listede = (liste || []).some(x => x.includes(yazi.slice(0, 30)));
  await ana(`(function(){var a=[].filter.call(document.querySelectorAll('#notlar .liste-li a'),function(a){return a.textContent===${JSON.stringify(ilk)}})[0];a&&a.click()})()`);
  const yeniden = await kadar(`document.getElementById('ok-not').textContent==='Not ●'&&document.getElementById('ok-not-metin').value===${JSON.stringify(yazi)}`, 8000);
  await tikla('#ok-not');
  diyalogKabul = true; await tikla('#ok-not-sil');
  const silindi = await kadar(`document.getElementById('ok-not').textContent==='Not'&&/not yok/.test(document.getElementById('ok-not-durum').textContent)`, 5000);
  await tikla('#ok-kapat');
  const kalan = (await (await fetch(TABAN + '/api/notlar')).json()).filter(n => n.metin === yazi).length;
  const tamam = !!kayit && dugme === 'Not ●' && !!ikinci && notBos === 'Not|true' && !!geri && !!ileri && listede && !!yeniden && !!silindi && kalan === 0 && (!!tam ? !!tamCik : true);
  return [tamam, `not kaydedildi: ${!!kayit} (düğme "${dugme}"); başka maddeye geçince not paneli kapandı ve düğme "${notBos.split('|')[0]}"; Geri → "${ilk}": ${!!geri}; İleri → "${ikinci}": ${!!ileri}; "Notlarım"da görünüyor: ${listede}; oradan açınca not yerinde: ${!!yeniden}; silince kalktı: ${!!silindi && kalan === 0}; tam ekran: ${tam ? 'açıldı ("' + tam + '"), kapandı: ' + !!tamCik : 'görünmez tarayıcıda açılamadı, sınanmadı'}`];
});

await senaryo('U42', 'Katalogda tür filtresi: türler sayılarıyla listeleniyor; bir türe basınca liste o kadar içeriğe iniyor; "Hepsi" geri getiriyor', async () => {
  await git('/uygulama/index.html#paketler');
  await kadar(`!!document.getElementById('katalog-btn')`);
  await tikla('#katalog-btn');
  const tur = await kadar(`document.querySelectorAll('#katalog-turler button').length>=3&&[].map.call(document.querySelectorAll('#katalog-turler button'),function(b){return b.childNodes[0].textContent+'='+b.querySelector('em').textContent})`, 40000);
  if (!tur) { const h = await ana(`document.getElementById('katalog-liste').innerText.slice(0,120)`); return [!(await ana(`!!document.getElementById('katalog-turler')`)) && /internet|bağlan|hata/i.test(h) ? 'ATLANDI' : false, 'tür düğmeleri çıkmadı: ' + h]; }
  const toplam = +tur[0].split('=')[1], sayilar = tur.slice(1).map(x => +x.split('=')[1]);
  await ana(`document.querySelectorAll('#katalog-turler button')[1].click()`);
  const secili = await ana(`({n:document.querySelectorAll('#katalog-liste ul.paket li').length,yazi:document.querySelector('#katalog-liste p.alt').textContent,aktif:document.querySelector('#katalog-turler button.aktif').childNodes[0].textContent})`);
  await resim('U42-katalog-turleri');
  await ana(`document.querySelector('#katalog-turler [data-kat-tur-hepsi]').click()`);
  const hepsi = await ana(`document.querySelectorAll('#katalog-liste ul.paket li').length`);
  const tamam = sayilar.reduce((a, b) => a + b, 0) === toplam && secili.n === sayilar[0] && hepsi === toplam;
  return [tamam, `türler: ${tur.join(', ')} (toplamları ${sayilar.reduce((a, b) => a + b, 0)}); "${secili.aktif}" seçilince ${secili.n} içerik ("${secili.yazi}"); "Hepsi" → ${hepsi}`];
});

await senaryo('U43', 'Başka bir İmece\'den kitap al: yazılan adresteki İmece\'nin kitapları listeleniyor, zaten olanlar "sende var" diye işaretli; tanınmayan adres nedeniyle reddediliyor', async () => {
  if (!(await ana(`!!document.getElementById('komsu-kart')`))) return [false, 'bu sürümde başka İmece\'den kitap alma yok'];
  const a = await ag(true);
  if (!a.acik || !a.adres) return ['ATLANDI', 'bu bilgisayar bir ağa bağlı değil'];
  try {
    await git('/uygulama/index.html#paketler');
    await kadar(`!!document.getElementById('komsu-btn')`);
    await ana(`(function(){document.getElementById('komsu-adres').value='merhaba';document.getElementById('komsu-btn').click()})()`);
    const red = await kadar(`(function(){var u=document.querySelector('#komsu-liste .uyari');return u&&u.textContent})()`, 5000);
    await ana(`(function(){document.getElementById('komsu-adres').value=${JSON.stringify(a.adres.replace('http://', '').replace(/\/$/, ''))};document.getElementById('komsu-btn').click()})()`);
    const liste = await kadar(`(function(){var l=document.querySelectorAll('#komsu-liste ul.paket li');return l.length&&{n:l.length,var:document.querySelectorAll('#komsu-liste .cip.var').length,al:document.querySelectorAll('#komsu-liste [data-komsu]').length,ust:document.querySelector('#komsu-liste p.alt').textContent}})()`, 12000);
    await resim('U43-baska-imeceden-al');
    const tamam = /Adres tanınmadı/.test(String(red)) && liste && liste.n === DURUM.zim_sayisi && liste.var === liste.n && liste.al === 0;
    return [tamam, `"merhaba" yazınca: "${String(red).slice(0, 50)}…"; doğru adresle: "${liste && liste.ust}", ${liste && liste.n} kitap listelendi, ${liste && liste.var} tanesi "sende var" (kendi kendine bağlandığı için hepsi), "Al" düğmesi: ${liste && liste.al}. Kopyalamanın kendisi sunucu senaryosunda (X3) sınandı.`];
  } finally { await ag(false); }
});

await senaryo('U38','Ayarlar → Aynı ağdaki cihazlarla paylaş: açınca adres ve "Ağa açık" işareti çıkıyor, o adresten kütüphane okunuyor; kapatınca adres kapanıyor', async () => {
  if (!DURUM.ag) return [false, 'bu sürümde ağ paylaşımı uygulamanın içinden açılamıyor'];
  await git('/uygulama/index.html#ayarlar');
  if (!await kadar(`document.getElementById('ag-btn').textContent==='Paylaşımı aç'&&/Kapalı/.test(document.getElementById('ag-durum').textContent)`, 5000)) return [false, 'paylaşım kartı beklenen durumda değil: ' + await ana(`document.getElementById('ag-durum').textContent`)];
  const rozet0 = await ana(`document.getElementById('ag-rozet').hidden`);
  await tikla('#ag-btn');
  const sonuc = await kadar(`document.getElementById('ag-btn').textContent==='Paylaşımı kapat'||document.getElementById('ag-durum').className==='uyari'`, 8000);
  const durum = await ana(`document.getElementById('ag-durum').textContent`);
  if (/ağa bağlı görünmüyor/.test(durum)) return ['ATLANDI', 'bu bilgisayar bir ağa bağlı değil: "' + durum + '"'];
  const adres = await ana(`document.getElementById('ag-adres').hidden?'':document.getElementById('ag-adres').textContent`);
  const rozet1 = await ana(`!document.getElementById('ag-rozet').hidden`);
  await resim('U38-ag-paylasimi');
  let agdan = null;
  try { const r = await (await fetch(adres + '/api/durum')).json(); agdan = { yerel: r.yerel, kitap: r.zim_sayisi }; } catch (e) { agdan = { hata: e.message }; }
  await tikla('#ag-btn');
  const kapandi = await kadar(`document.getElementById('ag-btn').textContent==='Paylaşımı aç'&&document.getElementById('ag-adres').hidden&&document.getElementById('ag-rozet').hidden`, 8000);
  let kapali = false;
  try { await fetch(adres + '/api/durum', { signal: AbortSignal.timeout(3000) }); } catch { kapali = true; }
  const tamam = !!sonuc && rozet0 && /^http:\/\/\d+\.\d+\.\d+\.\d+:\d+$/.test(adres) && !adres.includes('127.0.0.1') && rozet1 && agdan && agdan.yerel === false && agdan.kitap === DURUM.zim_sayisi && !!kapandi && kapali;
  return [tamam, `açınca: "${durum.slice(0, 80)}" ${adres}; üstte "Ağa açık" işareti: ${rozet1}; o adresten bağlanınca: ${JSON.stringify(agdan)}; kapatınca kart ve işaret eski hâlinde: ${!!kapandi}, adres kapandı: ${kapali}`];
});

await senaryo('U37','Kitap girişinde "Dosyayı denetle": kitap dosyasının sağlaması denetleniyor ve sonuç yazılıyor', async () => {
  await git('/uygulama/index.html#kutuphane');
  await kadar(`!!${kitapDugme(BUYUK)}`);
  await ana(`${kitapDugme(BUYUK)}.click()`);
  await kadar(`!!document.getElementById('kg-ara')`);
  if (!await kadar(`!!document.getElementById('kg-denetle')`, 4000)) return [false, 'giriş ekranında "Dosyayı denetle" düğmesi yok'];
  await tikla('#kg-denetle');
  const son = await kadar(`/^Sağlam/.test(document.getElementById('kg-denetle-durum').textContent)&&document.getElementById('kg-denetle-durum').textContent`, 60000);
  await resim('U37-kitap-denetle');
  const dugme = await ana(`!document.getElementById('kg-denetle').disabled`);
  await tikla('#kg-kapat');
  return [!!son && dugme, `sonuç: "${String(son).slice(0, 100)}"; düğme yeniden kullanılabilir: ${dugme}`];
});

// ---- Kitabı uygulamadan silme ve bilgisayardan ekleme ----
// Asıl kütüphaneden bir kitabı (Vikikitap) gerçekten siler ve yedeğinden geri ekler; bu yüzden yalnızca --kitap-sil-ekle ile çalışır.
const SILEKLE = process.argv.includes('--kitap-sil-ekle');
let yedek = null;
async function dosyaSec(sec, yol) { // dosya seçme penceresi yerine: seçilen dosyayı tarayıcıya doğrudan bildirir
  const r = await gonder('Runtime.evaluate', { expression: `document.querySelector(${JSON.stringify(sec)})` });
  await gonder('DOM.setFileInputFiles', { files: [yol], objectId: r.result.objectId });
  await ana(`document.querySelector(${JSON.stringify(sec)}).dispatchEvent(new Event('change'))`);
}
const kitapVarMi = async id => (await (await fetch(TABAN + '/api/kitaplar')).json()).some(k => k.id === id);

await senaryo('U35', 'Kitabı sil: giriş ekranındaki düğme onay soruyor; vazgeçince kitap duruyor; onaylayınca kitap, yer imi ve okuma geçmişi kalkıyor', async () => {
  if (!(await ana(`!!document.getElementById('ekle-kart')`))) return [false, 'bu sürümde uygulamadan kitap silme/ekleme yok'];
  if (!SILEKLE) return ['ATLANDI', 'asıl kütüphaneden bir kitabı silip geri eklediği için yalnızca --kitap-sil-ekle verilince çalışır'];
  const zdir = join(DURUM.veri, 'zim'), dosya = readdirSync(zdir).find(d => d.startsWith('wikibooks') && d.endsWith('.zim'));
  yedek = join(mkdtempSync(join(tmpdir(), 'imece-yedek-')), dosya);
  copyFileSync(join(zdir, dosya), yedek);
  if (!await maddeAc(VIKIKITAP, 'yemek')) return [false, 'madde açılamadı'];
  await kadar(`!!document.getElementById('ok-baslik').textContent`);
  if (await ana(`document.getElementById('ok-yerimi').textContent`) !== '★') await tikla('#ok-yerimi');
  await tikla('#ok-kapat');
  const SAY = `(function(){var f=function(a){return JSON.parse(localStorage.getItem(a)||'[]').filter(function(x){return x.kitap===${JSON.stringify(VIKIKITAP)}}).length};return {yerimi:f('imece-yerimi'),gecmis:f('imece-gecmis')}})()`;
  const once = await ana(SAY);
  if (!await kadar(`!!document.getElementById('kg-sil')`, 5000)) return [false, 'giriş ekranında "Bu kitabı sil" düğmesi yok'];
  diyalogKabul = false; await tikla('#kg-sil'); await bekle(1000);
  const soru = diyaloglar[diyaloglar.length - 1] || '';
  const duruyor = await kitapVarMi(VIKIKITAP);
  diyalogKabul = true; await tikla('#kg-sil');
  const bilgi = await kadar(`document.getElementById('kutuphane-bilgi').textContent`, 30000);
  await resim('U35-kitap-silindi');
  const sonra = await ana(SAY);
  const kart = await kadar(`!${kitapDugme(VIKIKITAP)}`, 5000);
  const gitti = !(await kitapVarMi(VIKIKITAP)) && !existsSync(join(zdir, dosya));
  const kapandi = await ana(`document.getElementById('kitap-ekran').hidden`);
  const tamam = /silinsin mi/.test(soru) && /geri alınamaz/.test(soru) && duruyor && !!bilgi && gitti && !!kart && kapandi && once.yerimi >= 1 && once.gecmis >= 1 && sonra.yerimi === 0 && sonra.gecmis === 0;
  return [tamam, `soru: "${soru.split('\n')[0]}" (geri alınamayacağını söylüyor: ${/geri alınamaz/.test(soru)}); vazgeçince kitap duruyor: ${duruyor}; onaylayınca: "${String(bilgi).slice(0, 70)}"; dosya ve kütüphane kartı gitti: ${gitti && !!kart}; bu kitaptaki yer imi ${once.yerimi} → ${sonra.yerimi}, geçmiş ${once.gecmis} → ${sonra.gecmis}`];
});

await senaryo('U36', 'Bilgisayardan kitap ekle: yanlış dosya nedeniyle reddediliyor; doğru dosya kopyalanıp kütüphaneye giriyor ve açılıyor; aynı dosya ikinci kez eklenmiyor', async () => {
  if (!(await ana(`!!document.getElementById('ekle-kart')`))) return [false, 'bu sürümde uygulamadan kitap silme/ekleme yok'];
  if (!SILEKLE || !yedek) return ['ATLANDI', 'yalnızca --kitap-sil-ekle verilince (U35 ile birlikte) çalışır'];
  await git('/uygulama/index.html#kutuphane');
  await kadar(`document.querySelectorAll('#kitaplar .kitap').length`);
  const cop = join(dirname(yedek), 'kitap-degil.zim');
  writeFileSync(cop, Buffer.alloc(5000, 7));
  await dosyaSec('#ekle-dosya', cop);
  const red = await kadar(`document.getElementById('ekle-durum').className==='uyari'&&document.getElementById('ekle-durum').textContent`, 10000);
  await dosyaSec('#ekle-dosya', yedek);
  const eklendi = await kadar(`/kütüphaneye eklendi/.test(document.getElementById('ekle-durum').textContent)&&document.getElementById('ekle-durum').textContent`, 90000);
  await resim('U36-kitap-eklendi');
  const kart = await kadar(`!!${kitapDugme(VIKIKITAP)}`, 8000);
  let hazir = false;
  for (let i = 0; i < 120 && !hazir; i++) { await bekle(500); const o = await (await fetch(TABAN + '/api/kitap?k=' + encodeURIComponent(VIKIKITAP))).json(); hazir = o.dizin && o.dizin.durum === 'hazir' && o.tam_metin.durum === 'hazir'; }
  const acildi = await maddeAc(VIKIKITAP, 'yemek');
  await tikla('#ok-kapat'); await tikla('#kg-kapat');
  await git('/uygulama/index.html#kutuphane');
  await kadar(`document.querySelectorAll('#kitaplar .kitap').length`);
  await dosyaSec('#ekle-dosya', yedek);
  const ikinci = await kadar(`document.getElementById('ekle-durum').className==='uyari'&&document.getElementById('ekle-durum').textContent`, 10000);
  const sayi = (await (await fetch(TABAN + '/api/kitaplar')).json()).filter(k => k.id.startsWith('wikibooks')).length;
  try { rmSync(dirname(yedek), { recursive: true, force: true }); } catch { }
  const tamam = /kitap \(ZIM\) dosyası değil/.test(String(red)) && !!eklendi && /sağlaması doğrulandı/.test(String(eklendi)) && !!kart && hazir && !!acildi && /zaten kütüphanende/.test(String(ikinci)) && sayi === 1;
  return [tamam, `kitap olmayan dosya: "${String(red).slice(0, 60)}…"; doğru dosya: "${String(eklendi).slice(0, 75)}…"; kütüphanede kart çıktı: ${!!kart}; dizinleri hazır: ${hazir}; madde açıldı: ${!!acildi}; aynı dosya ikinci kez: "${String(ikinci).slice(0, 50)}"; kütüphanede bu kitaptan ${sayi} tane`];
});

await senaryo('U26','Ayarlar → Hakkında: sürüm ve İmece\'nin hangi Python\'la çalıştığı yazıyor', async () => {
  if (!DURUM.calisma) return [false, 'bu sürüm hangi Python\'la çalıştığını bildirmiyor'];
  await git('/uygulama/index.html#ayarlar');
  const yazi = await kadar(`(function(){var t=document.getElementById('hakkinda').textContent;return t.indexOf('Python')>0?t:false})()`);
  return [!!yazi && yazi.includes(DURUM.surum) && yazi.includes(DURUM.calisma.python), `"${String(yazi).slice(0, 150)}"`];
});

await senaryo('U27', '"İmece\'yi kapat" düğmesi: onay soruyor; vazgeçince çalışmaya devam ediyor, onaylayınca kapanış ekranı çıkıyor ve İmece kapanıyor', async () => {
  if (!(await ana(`!!document.getElementById('imece-kapat')`))) return [false, 'kapatma düğmesi yok (İmece ancak siyah pencere kapatılarak kapanıyor)'];
  if (!process.argv.includes('--kapat')) return ['ATLANDI', 'sunucuyu kapattığı için yalnızca --kapat verilince çalışır'];
  await git('/uygulama/index.html#simdi');
  const gorunur = await kadar(`!document.getElementById('imece-kapat').hidden`);
  diyalogKabul = false; await tikla('#imece-kapat'); await bekle(1200);
  const soru = diyaloglar[diyaloglar.length - 1] || '';
  const hala = (await fetch(TABAN + '/api/durum')).ok, gizli = await ana(`document.getElementById('kapandi').hidden`);
  diyalogKabul = true; await tikla('#imece-kapat');
  const ekran = await kadar(`!document.getElementById('kapandi').hidden&&document.getElementById('kapandi').innerText`, 8000);
  await resim('U27-kapandi');
  let kapali = false;
  for (let i = 0; i < 40 && !kapali; i++) { await bekle(250); try { await fetch(TABAN + '/api/durum'); } catch { kapali = true; } }
  return [gorunur && /kapansın mı/.test(soru) && hala && gizli && !!ekran && kapali,
    `düğme görünür: ${!!gorunur}; soru: "${soru.split('\n')[0]}"; vazgeçince çalışıyor: ${hala}; onaylayınca ekran: "${String(ekran).replace(/\s+/g, ' ').slice(0, 90)}"; sunucu kapandı: ${kapali}`];
});

const g = SONUC.filter(s => s.durum === 'GEÇTİ').length, k = SONUC.filter(s => s.durum === 'KALDI').length;
console.log(`\nİmece ${DURUM.surum} arayüz: ${SONUC.length} senaryo, ${g} geçti, ${k} kaldı, ${SONUC.length - g - k} atlandı`);
if (arg('--json')) writeFileSync(arg('--json'), JSON.stringify({ surum: DURUM.surum, sonuc: SONUC }, null, 1));
ws.close(); tarayici.kill();
await bekle(800);
try { rmSync(profil, { recursive: true, force: true }); } catch { }
process.exit(0);
