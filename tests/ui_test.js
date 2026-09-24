const { JSDOM } = require('jsdom');
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://localhost/bots' });
const w = dom.window, d = w.document;
const XSS = '<img src=x onerror=alert(1)>Bot';
const now = Math.floor(Date.now() / 1000);
let names = [
  { name: 'DX1ABC-BOT', source: 'channel', messages: 8, last_heard: now - 60, auto: true, auto_reason: 'woord bot in de naam', manual: null, is_bot: true },
  { name: XSS, source: 'channel', messages: 1, last_heard: now - 20, auto: true, auto_reason: 'woord bot in de naam', manual: null, is_bot: true },
  { name: 'Echobot', source: 'contact', messages: 0, last_heard: now - 7000, auto: true, auto_reason: 'woord bot in de naam', manual: null, is_bot: true },
  { name: 'Alex', source: 'channel', messages: 30, last_heard: now - 30, auto: false, auto_reason: 'geen bot-kenmerk', manual: null, is_bot: false },
  { name: 'Talbot', source: 'channel', messages: 3, last_heard: now - 900, auto: true, auto_reason: 'woord bot in de naam', manual: false, is_bot: false },
];
const calls = []; let failNext = false;
w.fetch = (path, opts = {}) => {
  calls.push({ path, method: opts.method || 'GET', headers: opts.headers || {}, body: opts.body });
  const res = (ok, status, data) => Promise.resolve({ ok, status, json: () => Promise.resolve(data) });
  if (path === '/api/bots') return res(true, 200, { names, total: names.length });
  if (path === '/api/bots/set') {
    if (failNext) { failNext = false; return res(false, 400, { error: 'lijst vol (max 300)' }); }
    const { name, is_bot } = JSON.parse(opts.body);
    const i = names.findIndex(n => n.name.toLowerCase() === name.toLowerCase());
    const base = i >= 0 ? names[i] : { name, source: 'list', messages: 0, last_heard: 0, auto: /bot/i.test(name), auto_reason: 'x' };
    const manual = (is_bot === null || is_bot === base.auto) ? null : is_bot;
    const upd = { ...base, manual, is_bot: manual === null ? base.auto : manual };
    if (i >= 0) names[i] = upd; else names.push(upd);
    return res(true, 200, upd);
  }
  return res(false, 404, { error: 'onbekend' });
};
const tick = () => new Promise(r => setTimeout(r, 20));
let fails = 0;
const ok = (c, m) => { console.log((c ? 'OK   ' : 'FAIL ') + m); if (!c) fails++; };
const rowNames = () => [...d.querySelectorAll('#bots-body tr td:nth-child(2)')].map(td => td.textContent);
const scripts = [...d.querySelectorAll('script')].filter(s => !s.src && s.textContent.includes('bots-body'));
ok(scripts.length === 1, 'pagina-script gevonden');
w.eval(scripts[0].textContent);

(async () => {
  await tick();
  ok(calls[0] && calls[0].path === '/api/bots' && calls[0].headers['X-Requested-With'] === 'XMLHttpRequest', 'laadt /api/bots met X-Requested-With');
  ok(JSON.stringify(rowNames()) === JSON.stringify(['DX1ABC-BOT', XSS, 'Echobot']), 'standaardfilter toont alleen bots: ' + JSON.stringify(rowNames()));
  ok(d.querySelector('#bots-body img') === null && d.querySelectorAll('#bots-body *').length > 0, 'naam met HTML is tekst, geen element');
  ok(rowNames()[1] === XSS, 'naam met HTML wordt letterlijk getoond');
  ok(d.getElementById('n-bots').textContent === '3' && d.getElementById('n-people').textContent === '2' && d.getElementById('n-hand').textContent === '1' && d.getElementById('n-all').textContent === '5', 'tellers: 3 bots, 2 niet, 1 handmatig, 5 totaal');
  ok([...d.querySelectorAll('#bots-body input[type=checkbox]')].every(c => c.checked), 'alle bots zijn aangevinkt');
  ok(d.querySelector('#bots-body td:last-child').textContent === '8', 'aantal berichten getoond');
  ok(d.querySelectorAll('#bots-body td')[5 * 0 + 5].textContent === '8' && [...d.querySelectorAll('#bots-body tr')][2].lastChild.textContent === 'advert only', 'contact zonder berichten toont "advert only"');

  const filter = async v => { d.getElementById('f-' + v).checked = true; d.getElementById('f-' + v).dispatchEvent(new w.Event('change')); await tick(); };
  await filter('people');  ok(JSON.stringify(rowNames()) === JSON.stringify(['Alex', 'Talbot']), 'filter "Not bots": ' + JSON.stringify(rowNames()));
  await filter('hand');    ok(JSON.stringify(rowNames()) === JSON.stringify(['Talbot']), 'filter "Set by hand": ' + JSON.stringify(rowNames()));
  ok(d.querySelector('#bots-body .badge').textContent === 'By hand: not a bot', 'badge toont "By hand: not a bot"');
  await filter('all');     ok(rowNames().length === 5, 'filter "All": 5 rijen');
  const search = d.getElementById('bots-search'); search.value = 'ECHO'; search.dispatchEvent(new w.Event('input')); await tick();
  ok(JSON.stringify(rowNames()) === JSON.stringify(['Echobot']), 'zoeken (hoofdletterongevoelig): ' + JSON.stringify(rowNames()));
  search.value = 'zzz'; search.dispatchEvent(new w.Event('input')); await tick();
  ok(d.getElementById('bots-body').textContent.includes('Nothing matches'), 'lege zoekopdracht toont melding');
  search.value = ''; search.dispatchEvent(new w.Event('input')); await filter('bots');

  // uitvinken
  const box = d.querySelector('#bots-body input[type=checkbox]');   // DX1ABC-BOT
  box.checked = false; box.dispatchEvent(new w.Event('change')); await tick(); await tick();
  const post = calls.filter(c => c.path === '/api/bots/set').pop();
  ok(post && post.method === 'POST' && post.headers['X-Requested-With'] === 'XMLHttpRequest' && post.headers['Content-Type'] === 'application/json', 'POST met juiste kopjes');
  ok(post && JSON.parse(post.body).name === 'DX1ABC-BOT' && JSON.parse(post.body).is_bot === false, 'POST body: DX1ABC-BOT is_bot=false');
  ok(!rowNames().includes('DX1ABC-BOT'), 'rij verdwijnt uit het filter "Bots"');
  ok(d.querySelector('#bots-message .alert-success') && /DX1ABC-BOT now counts as not a bot \(by hand\)/.test(d.getElementById('bots-message').textContent), 'succesmelding');
  await filter('hand'); ok(rowNames().includes('DX1ABC-BOT') && rowNames().includes('Talbot'), 'DX1ABC-BOT staat bij "Set by hand"');

  // terug naar automatisch
  const reset = [...d.querySelectorAll('#bots-body button')].find(b => b.textContent === 'back to automatic');
  reset.click(); await tick(); await tick();
  const post2 = calls.filter(c => c.path === '/api/bots/set').pop();
  ok(JSON.parse(post2.body).is_bot === null, 'terug naar automatisch stuurt is_bot=null');
  await filter('bots'); ok(rowNames().includes('DX1ABC-BOT'), 'DX1ABC-BOT is weer bot (automatisch)');

  // toevoegen
  const add = d.getElementById('bots-add'); add.value = '  Nieuwe Bot Naam '; d.getElementById('bots-add-btn').click(); await tick(); await tick();
  const post3 = calls.filter(c => c.path === '/api/bots/set').pop();
  ok(JSON.parse(post3.body).name === 'Nieuwe Bot Naam' && JSON.parse(post3.body).is_bot === true, 'toevoegen stuurt schone naam met is_bot=true');
  ok(add.value === '', 'invoerveld wordt leeggemaakt');
  ok(rowNames().includes('Nieuwe Bot Naam'), 'nieuwe naam staat in de lijst');
  // Enter-toets
  add.value = 'Via Enter'; add.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); await tick(); await tick();
  ok(calls.filter(c => c.path === '/api/bots/set').pop().body.includes('Via Enter'), 'Enter voegt toe');
  // lege invoer
  add.value = '   '; d.getElementById('bots-add-btn').click(); await tick();
  ok(d.getElementById('bots-message').textContent.includes('Type a name first'), 'lege invoer geeft een waarschuwing');
  const before = calls.length;
  // fout van de server: vinkje wordt teruggezet en foutmelding getoond
  failNext = true;
  const box2 = d.querySelector('#bots-body input[type=checkbox]'); const nm = box2.closest('tr').children[1].textContent;
  box2.checked = false; box2.dispatchEvent(new w.Event('change')); await tick(); await tick();
  ok(d.querySelector('#bots-message .alert-danger') && d.getElementById('bots-message').textContent.includes('lijst vol'), 'foutmelding van de server getoond');
  ok(d.querySelector('#bots-body input[type=checkbox]').checked && rowNames().includes(nm), 'vinkje staat weer terug na een fout');
  console.log(`\n${fails} fouten`); process.exit(fails ? 1 : 0);
})();
