"""The single-page app served by server.py (HTML + inline CSS/JS).

Kept in its own module so server.py stays focused on the backend. The page is
fully self-contained and talks to the backend over the /api/* endpoints.

Style: an "editorial" look — serif headlines, a score-colored rail per story,
light-first with a dark toggle. Adds a model picker (datalist) and a row of
recommended one-click filter chips.
"""

PAGE = r"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>News Agent</title>
<style>
:root{
  --bg:#f7f6f3; --panel:#fffdfa; --card:#ffffff; --fg:#1b1b1f; --mut:#6b6f76;
  --line:#e6e3dc; --hi:#1a7f4b; --mid:#b4791b; --lo:#9aa0a8; --link:#3b3f8f;
  --accent:#3b3f8f; --chip:#f0eee8; --shadow:0 1px 3px rgba(0,0,0,.06),0 6px 18px rgba(0,0,0,.04);
  --serif:Georgia,"Iowan Old Style","Times New Roman",serif;
}
:root[data-theme="dark"]{
  --bg:#12141a; --panel:#171a21; --card:#1b1f28; --fg:#e9eaed; --mut:#9297a3;
  --line:#2a2e39; --hi:#3fb950; --mid:#d29922; --lo:#5b6270; --link:#9db4ff;
  --accent:#9db4ff; --chip:#232833; --shadow:none;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
a{color:var(--link)}
header{position:sticky;top:0;z-index:10;background:var(--panel);
 border-bottom:1px solid var(--line);padding:12px 22px}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:7px 0}
.brand{font-family:var(--serif);font-size:22px;font-weight:700;letter-spacing:-.01em}
.sub{color:var(--mut);font-size:12.5px}
.grp{display:flex;flex-wrap:wrap;gap:7px;align-items:center;
 background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:5px 9px}
.grp b{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--mut)}
label.chk{font-size:12.5px;display:flex;gap:4px;align-items:center;cursor:pointer;user-select:none}
input[type=text],input[type=password],input[type=search]{
 background:var(--card);border:1px solid var(--line);border-radius:8px;color:var(--fg);
 padding:7px 10px;font-size:13px}
input[type=search]{flex:1;min-width:180px}
button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:8px 16px;
 font-size:13px;font-weight:600;cursor:pointer}
button.ghost{background:transparent;color:var(--fg);border:1px solid var(--line);padding:7px 11px}
button:disabled{opacity:.5;cursor:default}
select{background:var(--card);border:1px solid var(--line);border-radius:8px;color:var(--fg);padding:7px}
.status{font-size:12.5px;color:var(--mut);display:flex;gap:8px;align-items:center}
.spin{width:13px;height:13px;border:2px solid var(--line);border-top-color:var(--accent);
 border-radius:50%;animation:sp .8s linear infinite;display:none}
.spin.on{display:inline-block}
@keyframes sp{to{transform:rotate(360deg)}}
.qf{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.qf b{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--mut);margin-right:2px}
.pill{background:var(--chip);color:var(--fg);border:1px solid var(--line);border-radius:20px;
 padding:3px 11px;font-size:12px;cursor:pointer;user-select:none}
.pill:hover{border-color:var(--accent);color:var(--accent)}
.pill.active{background:var(--accent);color:#fff;border-color:var(--accent)}
main{max-width:880px;margin:0 auto;padding:20px 22px 70px}
section h2{font-family:var(--serif);font-size:20px;font-weight:700;color:var(--fg);
 border-bottom:2px solid var(--line);padding-bottom:7px;margin:30px 0 12px;display:flex;
 justify-content:space-between;align-items:baseline}
section h2 .c{font-family:-apple-system,sans-serif;font-size:12px;color:var(--mut);font-weight:400}
.card{position:relative;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--rail,var(--lo));
 border-radius:8px;padding:14px 16px 14px 18px;margin:11px 0;box-shadow:var(--shadow);transition:transform .08s}
.card:hover{transform:translateY(-1px)}
.score{font-family:var(--serif);font-weight:700;font-size:15px;color:var(--rail,var(--lo));margin-right:8px}
.headline{color:var(--fg);text-decoration:none;font-family:var(--serif);font-weight:700;font-size:17.5px;line-height:1.3}
.headline:hover{color:var(--link)}
.meta{color:var(--mut);font-size:12px;margin-top:6px;text-transform:uppercase;letter-spacing:.03em}
.reason{color:var(--mut);font-size:13px;margin-top:7px;font-style:italic;font-family:var(--serif)}
.chips{margin-top:8px;display:flex;flex-wrap:wrap;gap:5px}
.chip{background:var(--chip);color:var(--mut);border-radius:20px;padding:1px 9px;font-size:11px}
.chip.aff{background:transparent;border:1px solid var(--accent);color:var(--accent);font-weight:600}
.alts{font-size:11.5px;margin-top:7px;color:var(--mut)}
.acts{position:absolute;right:12px;top:12px;display:flex;gap:8px}
.acts button{background:transparent;border:0;color:var(--lo);font-size:15px;padding:2px;cursor:pointer}
.acts button:hover,.acts button.on{color:var(--accent)}
.empty{color:var(--mut);font-style:italic;padding:44px 0;text-align:center;font-family:var(--serif)}
.notice{max-width:880px;margin:12px auto 0;padding:10px 14px;border-radius:9px;font-size:13px;
 font-weight:500;display:none;align-items:center;gap:8px}
.notice .x{margin-left:auto;cursor:pointer;opacity:.6;font-weight:700}
.notice.warn{background:#fff4e0;color:#7a4a00;border:1px solid #f0c674}
.notice.error{background:#fde8e8;color:#8a1c1c;border:1px solid #eaa0a0}
:root[data-theme="dark"] .notice.warn{background:#38300f;color:#f0cf8a;border-color:#6b5320}
:root[data-theme="dark"] .notice.error{background:#3a1c1c;color:#f0a8a8;border-color:#6b2626}
</style>
</head>
<body>
<header>
  <div class="row">
    <span class="brand">The Brief</span>
    <span class="sub" id="summary">not yet fetched</span>
    <span style="flex:1"></span>
    <button class="ghost" id="theme" title="toggle light/dark">◐</button>
  </div>
  <div class="row">
    <span class="grp" id="vendorsPremium"><b>Premium</b></span>
    <span class="grp" id="vendorsIndependent"><b>Independent</b></span>
    <span class="grp" id="sections"><b>Sections</b></span>
  </div>
  <div class="row">
    <input type="text" id="portfolio" placeholder="Portfolio (optional): NVDA 20%, TSM 15%, ASML 10% — blank = interest profile" style="flex:1;min-width:280px">
    <select id="pfselect" title="saved portfolios"><option value="">— saved —</option></select>
    <button class="ghost" id="pfsave" title="save current portfolio">Save</button>
    <button class="ghost" id="pfdel" title="delete selected portfolio">Delete</button>
  </div>
  <div class="row">
    <input type="password" id="key" placeholder="API key (blank = use .env)" style="width:210px">
    <select id="model" title="ranking model" style="min-width:210px"></select>
    <button id="refresh">Refresh</button>
    <span class="status"><span class="spin" id="spin"></span><span id="phase"></span></span>
  </div>
  <div class="row qf" id="quickfilters"><b>Quick filters</b></div>
  <div class="row">
    <input type="search" id="search" placeholder="filter by keyword, ticker, vendor...">
    <span class="grp"><b>Min score</b><input type="range" id="minscore" min="0" max="10" step="1" value="0"><span id="minval">0</span></span>
    <select id="sort">
      <option value="score">Sort: relevance</option>
      <option value="new">Sort: newest</option>
      <option value="vendor">Sort: vendor</option>
    </select>
    <select id="view">
      <option value="section">Group: section</option>
      <option value="holding">Group: holding</option>
    </select>
    <label class="chk"><input type="checkbox" id="staronly">★ only</label>
    <label class="chk"><input type="checkbox" id="showhidden">show hidden</label>
  </div>
</header>
<div class="notice" id="notice"></div>
<main id="main"><div class="empty">Pick your sources and press <b>Refresh</b> to fetch and rank today's news.</div></main>

<script>
const $ = s => document.querySelector(s);
const state = { items: [], cfg: null, generated: null,
  starred: new Set(JSON.parse(localStorage.getItem('starred')||'[]')),
  hidden: new Set(JSON.parse(localStorage.getItem('hidden')||'[]')) };

function saveSets(){
  localStorage.setItem('starred', JSON.stringify([...state.starred]));
  localStorage.setItem('hidden', JSON.stringify([...state.hidden]));
}
function esc(s){const d=document.createElement('div');d.textContent=s??'';return d.innerHTML;}
function ageLabel(h){
  if(h.age_hours==null) return '';
  const a=h.age_hours;
  if(a<1) return Math.round(a*60)+'m ago';
  if(a<24) return Math.round(a)+'h ago';
  return Math.round(a/24)+'d ago';
}
function railColor(s){return s>=7?'var(--hi)':s>=4?'var(--mid)':'var(--lo)';}
function chkboxes(host, values, cls){
  values.forEach(v=>{
    const l=document.createElement('label'); l.className='chk';
    l.innerHTML=`<input type="checkbox" class="${cls}" value="${esc(v)}" checked> ${esc(v)}`;
    host.appendChild(l);
  });
}
function checked(cls){return [...document.querySelectorAll('.'+cls+':checked')].map(c=>c.value);}

async function loadConfig(){
  const c = await (await fetch('/api/config')).json();
  state.cfg = c;
  const tiers = c.vendor_tiers || {};
  chkboxes($('#vendorsPremium'), c.vendors.filter(v=>(tiers[v]||'premium')==='premium'), 'v');
  chkboxes($('#vendorsIndependent'), c.vendors.filter(v=>tiers[v]==='independent'), 'v');
  chkboxes($('#sections'), c.sections, 's');
  // Model dropdown, grouped by provider so DeepSeek options are visible.
  const sel=$('#model');
  sel.innerHTML=`<option value="">default (${esc(c.model)})</option>`;
  const mk=(label,arr)=>{
    if(!arr.length) return;
    const og=document.createElement('optgroup'); og.label=label;
    arr.forEach(m=>{ const o=document.createElement('option'); o.value=m;
      o.textContent = m + (c.model===m?'  (current)':''); og.appendChild(o); });
    sel.appendChild(og);
  };
  mk('Gemini',   (c.models||[]).filter(m=>!m.startsWith('deepseek')));
  mk('DeepSeek', (c.models||[]).filter(m=>m.startsWith('deepseek')));
  if(!c.deepseek_key_present){
    [...sel.querySelectorAll('option')].forEach(o=>{
      if(o.value.startsWith('deepseek')) o.textContent += '  — needs DEEPSEEK_API_KEY';
    });
  }
  $('#key').placeholder = c.key_present ? 'API key set in .env (override optional)' : 'API key (none in .env)';
  const qf=$('#quickfilters');
  (c.filters||[]).forEach(f=>{
    const b=document.createElement('span'); b.className='pill'; b.textContent=f;
    b.onclick=()=>{
      const cur=$('#search').value.trim().toLowerCase();
      $('#search').value = (cur===f.toLowerCase()) ? '' : f;   // toggle
      updateActivePills(); render(state.generated);
    };
    qf.appendChild(b);
  });
}
function updateActivePills(){
  const q=$('#search').value.trim().toLowerCase();
  document.querySelectorAll('#quickfilters .pill').forEach(p=>
    p.classList.toggle('active', p.textContent.toLowerCase()===q));
}

function showNotice(n){
  const el=$('#notice');
  if(!n || !n.text){ el.style.display='none'; el.innerHTML=''; return; }
  el.className='notice '+(n.level==='error'?'error':'warn');
  el.innerHTML='⚠ '+esc(n.text)+'<span class="x" title="dismiss">✕</span>';
  el.querySelector('.x').onclick=()=>{ el.style.display='none'; };
  el.style.display='flex';
}

async function loadNews(){
  const d = await (await fetch('/api/news')).json();
  showNotice(d.notice);
  if(d.headlines && d.headlines.length){ state.items = d.headlines; render(d.generated); }
}

// --- Saved portfolios (localStorage) ----------------------------------------
function getPortfolios(){ return JSON.parse(localStorage.getItem('portfolios')||'{}'); }
function loadPortfolios(){
  let pf=getPortfolios();
  if(Object.keys(pf).length===0){   // seed a couple of examples on first use
    pf={"Semis-heavy":"NVDA 25%, TSM 20%, ASML 15%, AMD 12%, MU 12%, INTC 8%, TSEM 8%",
        "Mega-cap tech":"MSFT 20%, AAPL 20%, GOOG 20%, AMZN 20%, NVDA 20%",
        "AI compute":"NVDA 30%, TSM 20%, AMD 15%, MU 15%, ASML 10%, LITE 10%"};
    localStorage.setItem('portfolios',JSON.stringify(pf));
  }
  const sel=$('#pfselect');
  sel.innerHTML='<option value="">— saved —</option>'+
    Object.keys(pf).map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('');
}
$('#pfselect').onchange=()=>{
  const pf=getPortfolios(), v=$('#pfselect').value;
  if(v && pf[v]!==undefined) $('#portfolio').value=pf[v];
};
$('#pfsave').onclick=()=>{
  const txt=$('#portfolio').value.trim(); if(!txt){ alert('Enter a portfolio first.'); return; }
  const name=(prompt('Save this portfolio as:', $('#pfselect').value||'')||'').trim();
  if(!name) return;
  const pf=getPortfolios(); pf[name]=txt; localStorage.setItem('portfolios',JSON.stringify(pf));
  loadPortfolios(); $('#pfselect').value=name;
};
$('#pfdel').onclick=()=>{
  const v=$('#pfselect').value; if(!v) return;
  const pf=getPortfolios(); delete pf[v]; localStorage.setItem('portfolios',JSON.stringify(pf));
  loadPortfolios(); $('#portfolio').value='';
};

function passesFilter(h){
  const q = $('#search').value.trim().toLowerCase();
  if(state.hidden.has(h.url) && !$('#showhidden').checked) return false;
  if($('#staronly').checked && !state.starred.has(h.url)) return false;
  if((h.score??0) < parseFloat($('#minscore').value)) return false;
  if(q){
    const hay = (h.title+' '+h.vendor+' '+(h.reason||'')+' '+(h.keyword_hits||[]).join(' ')).toLowerCase();
    if(!hay.includes(q)) return false;
  }
  return true;
}

function sortItems(items){
  const mode = $('#sort').value;
  const s=[...items];
  if(mode==='new') s.sort((a,b)=>(a.age_hours==null?1e9:a.age_hours)-(b.age_hours==null?1e9:b.age_hours));
  else if(mode==='vendor') s.sort((a,b)=>a.vendor.localeCompare(b.vendor)||((b.score??0)-(a.score??0)));
  else s.sort((a,b)=>(b.score??0)-(a.score??0));
  return s;
}

function card(h){
  const s = h.score==null?0:Math.round(h.score);
  const rail = railColor(s);
  const el=document.createElement('article'); el.className='card'; el.style.setProperty('--rail',rail);
  const aff=(h.affects||[]).slice(0,4).map(a=>`<span class="chip aff">${esc(a.ticker)}${a.channel?'·'+esc(a.channel):''}</span>`).join('');
  const kw=(h.keyword_hits||[]).slice(0,6).map(k=>`<span class="chip">${esc(k)}</span>`).join('');
  const chips=aff+kw;
  const alts=(h.alternates&&h.alternates.length)
    ? `<div class="alts">also at ${h.alternates.map(a=>`<a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.vendor)}</a>`).join(' · ')}</div>`:'';
  const star = state.starred.has(h.url)?'on':'';
  el.innerHTML=`
    <div class="acts">
      <button class="star ${star}" title="star">★</button>
      <button class="hide" title="hide">✕</button>
    </div>
    <a class="headline" href="${esc(h.url)}" target="_blank" rel="noopener"><span class="score">${s}</span>${esc(h.title)}</a>
    <div class="meta">${esc(h.vendor)}${ageLabel(h)?' · '+ageLabel(h):''}</div>
    ${h.reason?`<div class="reason">${esc(h.reason)}</div>`:''}
    ${chips?`<div class="chips">${chips}</div>`:''}
    ${alts}`;
  el.querySelector('.star').onclick=()=>{
    if(state.starred.has(h.url))state.starred.delete(h.url);else state.starred.add(h.url);
    saveSets(); render(state.generated);
  };
  el.querySelector('.hide').onclick=()=>{ state.hidden.add(h.url); saveSets(); render(state.generated); };
  return el;
}

function render(generated){
  state.generated = generated;
  const main=$('#main'); main.innerHTML='';
  const secOrder = state.cfg ? state.cfg.sections : ['Business','Technology','World'];
  const visible = sortItems(state.items.filter(passesFilter));
  $('#summary').textContent = generated
    ? `${visible.length} shown · ${state.items.length} ranked · updated ${new Date(generated).toLocaleString()}`
    : `${visible.length} shown`;
  if(!visible.length){ main.innerHTML='<div class="empty">Nothing matches the current filters.</div>'; return; }

  const holdingView = $('#view').value==='holding'
    && state.items.some(h=>h.affects && h.affects.length);
  const groups = {};      // groupName -> [headlines]
  let order;
  if(holdingView){
    visible.forEach(h=>{
      const ts=[...new Set((h.affects||[]).map(a=>a.ticker))];
      (ts.length?ts:['(other)']).forEach(t=>{(groups[t]=groups[t]||[]).push(h);});
    });
    order = Object.keys(groups).sort((a,b)=>groups[b].length-groups[a].length);
  } else {
    visible.forEach(h=>{(groups[h.section]=groups[h.section]||[]).push(h);});
    order = secOrder.filter(s=>groups[s]);
  }
  order.forEach(g=>{
    const items=groups[g]; if(!items||!items.length) return;
    const s=document.createElement('section');
    s.innerHTML=`<h2>${esc(g)}<span class="c">${items.length} stories</span></h2>`;
    items.forEach(h=>s.appendChild(card(h)));
    main.appendChild(s);
  });
}

let polling=null;
// Attach the UI to whatever job is running server-side and poll it to completion.
// Used both after we start a refresh AND when a refresh is already in flight, so
// any window (or a reload) reflects the true backend state instead of hanging.
function attachToJob(){
  $('#refresh').disabled=true; $('#spin').classList.add('on');
  clearInterval(polling);
  polling=setInterval(async()=>{
    let st;
    try{ st=await (await fetch('/api/status')).json(); }
    catch(e){ return; }   // transient; keep polling
    $('#phase').textContent = st.phase + (st.running?'…':'');
    if(!st.running){
      clearInterval(polling); $('#refresh').disabled=false; $('#spin').classList.remove('on');
      if(st.error){ $('#phase').textContent='error: '+st.error; return; }
      await loadNews(); $('#phase').textContent='updated';
    }
  },1000);
}
async function refresh(){
  const body={ vendors:checked('v'), sections:checked('s'),
               key:$('#key').value, model:$('#model').value,
               portfolio:$('#portfolio').value };
  const r=await (await fetch('/api/refresh',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)})).json();
  // Attach whether we started it or one was already running; only bail on a real error.
  if(!r.started && !/already running/i.test(r.error||'')){
    $('#phase').textContent=r.error||'busy'; return;
  }
  attachToJob();
}

$('#refresh').onclick=refresh;
$('#search').oninput=()=>{updateActivePills(); render(state.generated);};
$('#sort').onchange=()=>render(state.generated);
$('#view').onchange=()=>render(state.generated);
$('#portfolio').addEventListener('keydown',e=>{ if(e.key==='Enter') refresh(); });
$('#staronly').onchange=()=>render(state.generated);
$('#showhidden').onchange=()=>render(state.generated);
$('#minscore').oninput=e=>{ $('#minval').textContent=e.target.value; render(state.generated); };
$('#theme').onclick=()=>{
  const cur=document.documentElement.getAttribute('data-theme');
  const next=cur==='dark'?'light':'dark';
  document.documentElement.setAttribute('data-theme',next);
  localStorage.setItem('theme',next);
};
(function initTheme(){const t=localStorage.getItem('theme'); if(t)document.documentElement.setAttribute('data-theme',t);})();

// On load: populate controls, show any existing results, and if a refresh is
// already running (e.g. started elsewhere), attach to it and show progress.
// Heartbeat: tells the server the tab is still open. When every tab is closed
// the beats stop and the server auto-shuts down (~12s later). Survives reloads
// and multiple tabs (any open tab keeps it alive).
function beat(){ fetch('/api/heartbeat',{method:'POST',keepalive:true}).catch(()=>{}); }
beat();
setInterval(beat, 3000);

async function init(){
  await loadConfig();
  loadPortfolios();
  await loadNews();
  try{
    const st=await (await fetch('/api/status')).json();
    if(st.running) attachToJob();
  }catch(e){}
}
init();
</script>
</body>
</html>
"""
