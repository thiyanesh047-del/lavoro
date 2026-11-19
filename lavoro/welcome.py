"""The welcome screen: drop a CV (or paste a portfolio link) → check your profile and preferences → first search.

Three panels on one page over the valley:
  1. start     — centered headline and one input bar; dropping a file anywhere on the page works too
  2. you       — what Lavoro read, plus roles / cities / links, pre-filled from the CV
  3. searching — live progress of the first run, then on to today's list
"""
from __future__ import annotations

import json

from .digest import CSS as BASE_CSS
from .digest import JS as BASE_JS
from .digest import e, head, icon, scene

EXTRA_ICONS = {
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "arrow": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "sliders": '<path d="M4 6h10"/><path d="M18 6h2"/><circle cx="16" cy="6" r="2"/><path d="M4 18h4"/><path d="M12 18h8"/><circle cx="10" cy="18" r="2"/><path d="M4 12h2"/><path d="M10 12h10"/><circle cx="8" cy="12" r="2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "building": '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"/>',
    "spark": '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
    "brief": '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>',
    "people": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "left": '<path d="m15 18-6-6 6-6"/>',
}


def ic(name: str) -> str:
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{EXTRA_ICONS[name]}</svg>') if name in EXTRA_ICONS else icon(name)


CSS = r"""
body.welcome{min-height:100vh}
body.welcome main::before{display:none}  /* the dashboard's white lift-off layer would cover the valley here */
.panel{display:none}.panel.on{display:block;animation:rise .7s var(--ease) both}
@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}

/* 1. start */
.start{min-height:calc(100vh - 64px);display:none;flex-direction:column;align-items:center;justify-content:center;
  text-align:center;padding:4vh 20px 18vh}
.start.on{display:flex}
.start{position:relative;isolation:isolate}
.start::before{content:"";position:absolute;z-index:-1;left:50%;top:46%;width:min(1100px,140vw);height:min(760px,95vh);
  transform:translate(-50%,-50%);border-radius:50%;filter:blur(30px);
  background:radial-gradient(closest-side,rgba(252,250,246,.88),rgba(252,250,246,.55) 55%,rgba(252,250,246,0))}
.start h1{max-width:13ch;margin:0 auto;font-size:clamp(46px,7.8vw,92px)}
.start .lede{max-width:46ch;margin:22px auto 0;font:500 17.5px/1.6 var(--sans);color:#1f1f1f;
  text-shadow:0 1px 18px rgba(255,252,248,.9)}
.drop{margin:34px auto 0;width:min(640px,100%);display:flex;align-items:center;gap:8px;padding:8px;border-radius:20px;
  background:rgba(255,255,255,.94);box-shadow:0 0 0 1px rgba(255,255,255,.8) inset,0 18px 50px -18px rgba(30,40,30,.45);
  transition:box-shadow .3s,transform .3s var(--ease)}
.drop:focus-within{box-shadow:0 0 0 2px rgba(225,29,72,.35),0 18px 50px -18px rgba(30,40,30,.45)}
.chipbtn{flex:none;width:46px;height:46px;border-radius:13px;border:0;display:grid;place-items:center;cursor:pointer;color:#fff;
  transition:transform .15s}
.chipbtn:hover{transform:translateY(-1px)}.chipbtn svg{width:20px;height:20px}
.chipbtn.file{background:var(--rose)}.chipbtn.link{background:#1f2a24;margin-left:-4px}
.drop input[type=text]{flex:1;min-width:0;height:46px;border:0;outline:0;background:transparent;font:500 16.5px var(--sans);
  color:var(--ink);padding:0 6px}
.drop input::placeholder{color:#707070}
.go-btn{flex:none;min-height:50px;padding:0 22px;border:0;border-radius:14px;background:var(--rose);color:#fff;cursor:pointer;
  font:700 16px/1 var(--sans);display:inline-flex;align-items:center;gap:10px;box-shadow:0 10px 24px -6px var(--rose-glow);
  transition:background .2s,box-shadow .2s}
.go-btn:hover{background:var(--rose-ink)}.go-btn[disabled]{opacity:.75;cursor:progress}
.go-btn svg{width:18px;height:18px}
.go-btn .spin{width:16px;height:16px;border-radius:50%;border:2px solid rgba(255,255,255,.45);border-top-color:#fff;
  animation:spin .9s linear infinite;display:none}
.go-btn.busy .spin{display:inline-block}.go-btn.busy svg{display:none}
.hint{margin:14px auto 0;max-width:56ch;font-size:13.5px;color:#2b2b2b;text-shadow:0 1px 12px rgba(255,252,248,.95)}
.hint b{font-weight:600}
.err{margin:12px auto 0;max-width:60ch;display:none;padding:10px 14px;border-radius:12px;background:var(--rose-wash);
  color:var(--rose-ink);font-size:14px;box-shadow:0 0 0 1px rgba(253,164,175,.9) inset;text-align:left}
.err.on{display:block}
.status-line{margin-top:12px;min-height:22px;font-size:14px;color:#222;text-shadow:0 1px 12px rgba(255,252,248,.95)}
.dropzone{position:fixed;inset:12px;z-index:20;border-radius:24px;border:2px dashed rgba(225,29,72,.6);
  background:rgba(251,250,248,.72);backdrop-filter:blur(6px);display:grid;place-items:center;opacity:0;pointer-events:none;
  transition:opacity .2s}
.dropzone.on{opacity:1}
.dropzone p{font:400 44px/1 var(--serif);margin:0}

/* 2. you  /  3. searching */
.sheet{max-width:680px;margin:6vh auto 12vh;padding:32px;border-radius:22px;background:rgba(255,255,255,.95);
  box-shadow:0 0 0 1px var(--line) inset,0 30px 80px -30px rgba(30,40,30,.45)}
.sheet h2{margin:0;font:400 44px/1.05 var(--serif);letter-spacing:-.015em}
.sheet .sub{margin:10px 0 0;font-size:15px;color:var(--ink-2)}
.read{margin-top:18px;border:1px solid var(--line);border-radius:14px;background:var(--inset)}
.read summary{cursor:pointer;padding:12px 16px;font-weight:600;font-size:14.5px;display:flex;justify-content:space-between;gap:12px}
.read summary span{font-weight:500;color:var(--mute)}
.read pre{margin:0;padding:0 16px 16px;white-space:pre-wrap;font:400 13.5px/1.65 var(--sans);color:#2a2a2a;max-height:360px;overflow:auto}
.form{display:grid;gap:18px;margin-top:24px}
.field label,.field .lbl{display:block;font-weight:600;font-size:14px;margin-bottom:6px}
.field .help{font-size:12.5px;color:var(--mute);margin-top:5px}
.field input[type=text],.field input[type=url]{width:100%;height:46px;border-radius:12px;border:1px solid var(--line);
  background:#fff;padding:0 14px;font:500 15px var(--sans);color:var(--ink);outline:0;transition:border-color .2s,box-shadow .2s}
.field input:focus{border-color:rgba(225,29,72,.5);box-shadow:0 0 0 3px rgba(225,29,72,.12)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.chips{display:flex;flex-wrap:wrap;gap:8px;padding:8px;min-height:50px;border-radius:12px;border:1px solid var(--line);background:#fff;
  cursor:text;transition:border-color .2s,box-shadow .2s}
.chips:focus-within{border-color:rgba(225,29,72,.5);box-shadow:0 0 0 3px rgba(225,29,72,.12)}
.chip{display:inline-flex;align-items:center;gap:4px;height:32px;padding:0 6px 0 12px;border-radius:999px;background:#f2f1ed;
  font:500 14px var(--sans)}
.chip button{border:0;background:transparent;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;cursor:pointer;
  color:var(--mute)}
.chip button:hover{background:#e6e4de;color:var(--ink)}.chip button svg{width:14px;height:14px}
.chips input{flex:1;min-width:140px;border:0;outline:0;font:500 15px var(--sans);height:32px;background:transparent}
.check{display:flex;gap:12px;align-items:flex-start;padding:12px 14px;border-radius:12px;border:1px solid var(--line);cursor:pointer;
  background:#fff}
.check input{width:18px;height:18px;margin:2px 0 0;accent-color:var(--rose)}
.check b{display:block;font-weight:600;font-size:14.5px}.check span{font-size:13px;color:var(--mute)}
.actions-row{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:6px;flex-wrap:wrap}
.linkish{border:0;background:transparent;color:var(--mute);font:500 14px var(--sans);cursor:pointer;padding:8px 0}
.linkish:hover{color:var(--ink)}
/* 3. the live timeline: one card that fills in, step by step, with real results */
.tl-card{max-width:720px;margin:5vh auto 12vh;border-radius:24px;background:rgba(255,255,255,.96);overflow:hidden;
  box-shadow:0 0 0 1px var(--line) inset,0 30px 80px -30px rgba(30,40,30,.45)}
.tl-head{display:flex;align-items:center;gap:14px;padding:18px 22px;border-bottom:1px solid var(--line)}
.tl-head .mark{width:34px;height:34px;border-radius:10px;background:var(--rose);color:#fff;display:grid;place-items:center;flex:none}
.tl-head .mark svg{width:17px;height:17px}
.tl-head b{display:block;font-size:15.5px}.tl-head small{color:var(--mute);font-size:12.5px}
.tl-clock{margin-left:auto;display:inline-flex;align-items:center;gap:8px;height:30px;padding:0 12px;border-radius:999px;
  background:#f6f5f1;font:600 13px/1 var(--sans);font-variant-numeric:tabular-nums;white-space:nowrap}
.tl-clock i{width:8px;height:8px;border-radius:50%;background:var(--rose);animation:pulse 1.4s ease-in-out infinite}
.tl-clock.done i{display:none}
@keyframes pulse{50%{opacity:.25}}
.tl{list-style:none;margin:0;padding:6px 22px 14px}
.tl>li{display:grid;grid-template-columns:40px 1fr 26px;gap:0 14px;padding:16px 0;border-top:1px solid var(--line);transition:opacity .4s}
.tl>li:first-child{border-top:0}
.tl>li.pending{opacity:.38}
.tl>li[hidden]{display:none}
.tl .ico{width:40px;height:40px;border-radius:12px;display:grid;place-items:center;color:#fff}
.tl .ico svg{width:19px;height:19px}
.tl .t{font-weight:650;font-size:15.5px;line-height:1.35;margin-top:2px}
.tl .s{color:var(--mute);font-size:13px;margin-top:2px}
.tl .body{grid-column:2/4;margin-top:10px;min-width:0}
.tl .body:empty{display:none}
.tl .state{width:24px;height:24px;border-radius:50%;margin-top:4px;display:grid;place-items:center}
.tl .state svg{width:14px;height:14px;display:none}
.tl li.done .state{background:var(--mint);color:#fff}
.tl li.done .state svg{display:block}
.tl li.active .state{border:2px solid rgba(225,29,72,.2);border-top-color:var(--rose);animation:spin .9s linear infinite}
.tl li.pending .state{box-shadow:0 0 0 1.5px var(--line) inset}
.c-rose{background:#e11d48}.c-sky{background:#0284c7}.c-pink{background:#db2777}.c-amber{background:#d97706}
.c-green{background:#059669}.c-violet{background:#7c3aed}.c-red{background:#dc2626}.c-ink{background:#1f2a24}
.pills{display:flex;flex-wrap:wrap;gap:7px}
.pl{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 11px;border-radius:999px;font:600 12.5px/1 var(--sans);
  background:#f3f1ec;color:var(--ink-2);white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis}
.pl b{font-weight:700;color:var(--ink);font-variant-numeric:tabular-nums}
.pl.ok::before{content:"\2713";color:var(--mint-ink)}
.pl.org{background:#fff;box-shadow:0 0 0 1px var(--line) inset}
.pl.k1{background:#e0f2fe;color:#075985}.pl.k2{background:#fef3c7;color:#92400e}.pl.k3{background:#dcfce7;color:#166534}
.pl.k4{background:#ede9fe;color:#5b21b6}.pl.k5{background:#ffe4e6;color:#9f1239}
.pills+.pills{margin-top:8px}
.cards{display:flex;gap:12px;overflow-x:auto;overflow-y:hidden;scroll-snap-type:x mandatory;padding:2px 2px 8px;scrollbar-width:none}
.cards::-webkit-scrollbar{display:none}
.jc{flex:0 0 200px;scroll-snap-align:start;border-radius:16px;background:#fff;box-shadow:0 0 0 1px var(--line) inset;
  overflow:hidden;text-decoration:none;color:inherit;display:flex;flex-direction:column;transition:transform .2s var(--ease)}
.jc:hover{transform:translateY(-2px)}
.jc .top{height:58px;position:relative;background:var(--tint,#e0f2fe)}
.jc .av{position:absolute;left:14px;bottom:-18px;width:38px;height:38px;border-radius:11px;background:#fff;display:grid;
  place-items:center;font:700 16px/1 var(--sans);box-shadow:0 2px 8px rgba(0,0,0,.12)}
.jc .age{position:absolute;right:10px;top:10px;height:22px;padding:0 9px;border-radius:999px;background:rgba(255,255,255,.88);
  font:600 11px/22px var(--sans)}
.jc .in{padding:26px 14px 14px;display:flex;flex-direction:column;gap:4px;flex:1}
.jc .co{font-weight:650;font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.jc .ti{font:400 18px/1.15 var(--serif);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.jc .lo{margin-top:auto;padding-top:8px;font-size:12px;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.jc .sc{font:600 12px var(--sans);color:var(--mint-ink)}
.swipe{display:flex;align-items:center;justify-content:space-between;margin-top:4px;font-size:12.5px;color:var(--mute)}
.swipe button{width:30px;height:30px;border-radius:50%;border:0;background:#f3f1ec;cursor:pointer;display:inline-grid;place-items:center;margin-left:6px;color:var(--ink)}
.swipe button svg{width:15px;height:15px}
.pr{display:grid;grid-template-columns:30px minmax(0,1fr) auto;gap:10px;align-items:center;padding:7px 0}
.pr .av{width:30px;height:30px;border-radius:9px;background:#f3f1ec;display:grid;place-items:center;font:700 13px var(--sans)}
.pr b{display:block;font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pr small{color:var(--mute);font-size:12.5px}
.pr .em{font:500 12.5px var(--sans);color:var(--ink-2);text-align:right;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rc{flex:0 0 230px;scroll-snap-align:start;border-radius:16px;background:#fff;box-shadow:0 0 0 1px var(--line) inset;padding:14px;
  text-decoration:none;color:inherit;display:flex;flex-direction:column;gap:6px}
.rc b{font-size:14.5px}.rc .amt{font:600 12px var(--sans);color:var(--amber-ink)}
.rc p{margin:0;font-size:12.5px;color:var(--ink-2);line-height:1.45;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.rc .rl{margin-top:auto;font:600 12px var(--sans);color:var(--mute)}
.more{font-size:12.5px;color:var(--mute);margin-top:6px}
.empty-s{font-size:13.5px;color:var(--ink-2);margin:0}
.tl-foot{padding:0 22px 22px;display:none;gap:12px;align-items:center;flex-wrap:wrap}
.tl-foot.on{display:flex}
.tl-foot .go-btn{text-decoration:none}
.tl-foot p{margin:0;font-size:13.5px;color:var(--mute);flex:1 1 240px}
.note{margin-top:18px;font-size:13.5px;color:var(--mute)}

@media (max-width:640px){
  .start{padding:2vh 16px 12vh}
  .drop{flex-wrap:wrap;padding:8px}
  .drop input[type=text]{flex:1 1 60%;font-size:16px}
  .chipbtn.link{display:none}
  .go-btn{width:100%;justify-content:center}
  .sheet{margin:3vh 12px 8vh;padding:22px}
  .sheet h2{font-size:36px}
  .two{grid-template-columns:1fr}
  .tl-card{margin:3vh 10px 8vh;border-radius:20px}
  .tl{padding:4px 16px 10px}.tl-head{padding:14px 16px}.tl-foot{padding:0 16px 18px}
  .tl>li{grid-template-columns:34px 1fr 24px;gap:0 10px}
  .tl .ico{width:34px;height:34px;border-radius:10px}
  .tl .body{grid-column:1/4}
  .jc{flex-basis:170px}
  .pr{grid-template-columns:30px minmax(0,1fr)}
  .pr .em{grid-column:2;text-align:left;white-space:normal;word-break:break-all}
}
"""

JS = r"""
const $=s=>document.querySelector(s);
const panels={start:$('#p-start'),you:$('#p-you'),go:$('#p-go')};
function show(name){Object.values(panels).forEach(p=>p.classList.remove('on'));panels[name].classList.add('on');scrollTo({top:0,behavior:'smooth'})}
if(matchMedia('(max-width: 640px)').matches) $('#source').placeholder='Link, or drop your CV';
const err=$('#err'), go=$('#go'), input=$('#source'), fileIn=$('#file'), statusEl=$('#status');
function fail(msg){err.textContent=msg;err.classList.add('on');go.disabled=false;go.classList.remove('busy');statusEl.textContent=''}
function busy(steps){err.classList.remove('on');go.disabled=true;go.classList.add('busy');let i=0;statusEl.textContent=steps[0];
  clearInterval(window._t);window._t=setInterval(()=>{i=Math.min(i+1,steps.length-1);statusEl.textContent=steps[i]},9000)}
function done(){clearInterval(window._t);go.disabled=false;go.classList.remove('busy');statusEl.textContent=''}
async function post(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json().catch(()=>({error:'The server sent an unreadable answer.'}));if(!r.ok)throw new Error(d.error||r.statusText);return d}

/* 1. start: a file or a link */
async function useFile(f){
  if(!f)return; if(!/\.(pdf|docx|txt|md)$/i.test(f.name)) return fail('Use a PDF, Word (.docx) or text file.');
  if(f.size>15*1024*1024) return fail('That file is over 15 MB. Export a smaller PDF.');
  input.value=f.name; busy(['Reading '+f.name+'…','Pulling out your experience…','Writing your profile…','Almost there…']);
  const data=await new Promise((res,rej)=>{const rd=new FileReader();rd.onload=()=>res(String(rd.result).split(',')[1]);rd.onerror=rej;rd.readAsDataURL(f)});
  try{fill(await post('/api/profile/upload',{name:f.name,data}),'your CV')}catch(e){fail(e.message)}
}
async function useLink(url){
  if(!url) return fail('Paste a link to your portfolio, or drop your CV.');
  if(/linkedin\.com/i.test(url)) return fail('LinkedIn doesn\'t let other tools read profiles. On LinkedIn choose More → Save to PDF, then drop that PDF here.');
  busy(['Opening your site…','Reading your projects…','Writing your profile…','Almost there…']);
  try{fill(await post('/api/profile/link',{url}),'your site')}catch(e){fail(e.message)}
}
$('#pick').addEventListener('click',()=>fileIn.click());
$('#paste').addEventListener('click',()=>{input.value='';input.placeholder='https://your-portfolio.com';input.focus()});
fileIn.addEventListener('change',()=>useFile(fileIn.files[0]));
$('#startform').addEventListener('submit',ev=>{ev.preventDefault();const v=input.value.trim();
  if(fileIn.files[0]&&v===fileIn.files[0].name) return useFile(fileIn.files[0]); useLink(v)});
const dz=$('.dropzone');let depth=0;
addEventListener('dragenter',ev=>{if(!panels.start.classList.contains('on'))return;ev.preventDefault();depth++;dz.classList.add('on')});
addEventListener('dragleave',()=>{depth=Math.max(0,depth-1);if(!depth)dz.classList.remove('on')});
addEventListener('dragover',ev=>ev.preventDefault());
addEventListener('drop',ev=>{ev.preventDefault();depth=0;dz.classList.remove('on');if(panels.start.classList.contains('on'))useFile(ev.dataTransfer.files[0])});

/* 2. you: chips + preferences */
function chipField(el,values){
  const box=el, inp=box.querySelector('input'); let vals=[];
  function render(){box.querySelectorAll('.chip').forEach(c=>c.remove());vals.forEach((v,i)=>{const c=document.createElement('span');c.className='chip';
    c.innerHTML='<span></span><button type="button" aria-label="Remove">'+document.getElementById('xicon').innerHTML+'</button>';
    c.firstChild.textContent=v;c.querySelector('button').onclick=()=>{vals.splice(i,1);render()};box.insertBefore(c,inp)})}
  function add(v){v=v.trim().toLowerCase();if(v&&!vals.includes(v))vals.push(v);render()}
  inp.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===','){ev.preventDefault();add(inp.value);inp.value=''}
    else if(ev.key==='Backspace'&&!inp.value&&vals.length){vals.pop();render()}});
  inp.addEventListener('blur',()=>{if(inp.value.trim()){add(inp.value);inp.value=''}});
  box.addEventListener('click',()=>inp.focus());
  (values||[]).forEach(add); return {get:()=>vals};
}
let titles, cities;
function fill(d,src){
  done(); const first=d.first_name||(d.name||'').split(' ')[0];
  $('#hello').textContent=first?`Nice to meet you, ${first}.`:'Nice to meet you.';
  $('#took').textContent=d.headline?`${d.headline}`:'';
  $('#src').textContent=src; $('#md').textContent=d.markdown;
  const todos=(d.markdown.match(/TODO/g)||[]).length; $('#todos').textContent=todos?`${todos} thing${todos>1?'s':''} to fill in later`:'';
  $('#f-name').value=d.name||''; $('#f-portfolio').value=d.portfolio_url||''; $('#f-linkedin').value=d.linkedin_url||'';
  $('#f-sweden').checked=!!d.in_sweden;
  titles=chipField($('#titles'),d.suggested_titles); cities=chipField($('#cities'),d.suggested_locations);
  show('you');
}
$('#back').addEventListener('click',()=>show('start'));
$('#youform').addEventListener('submit',async ev=>{ev.preventDefault();const b=$('#findbtn');b.disabled=true;b.classList.add('busy');
  try{
    await post('/api/preferences',{name:$('#f-name').value,portfolio:$('#f-portfolio').value,linkedin:$('#f-linkedin').value,
      titles:titles.get(),locations:cities.get(),remote_ok:$('#f-remote').checked,in_sweden:$('#f-sweden').checked});
    const r=await post('/api/run',{}); startProgress(r.discover);
  }catch(e){$('#youerr').textContent=e.message;$('#youerr').classList.add('on');b.disabled=false;b.classList.remove('busy')}});

/* 3. the live timeline */
const ORDER=['Starting','Finding companies','Fetching jobs','Searching the web','Checking who just raised','Scoring roles','Finding people','Writing emails','Finishing'];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const TINTS=['#e0f2fe','#dcfce7','#fef3c7','#ede9fe','#ffe4e6','#e0e7ff','#ccfbf1'];
const tint=s=>TINTS[[...String(s)].reduce((a,c)=>a+c.charCodeAt(0),0)%TINTS.length];
function ago(iso){if(!iso)return'';const d=(Date.now()-new Date(iso).getTime())/864e5;
  return d<1?'today':d<2?'yesterday':d<30?Math.floor(d)+'d ago':Math.floor(d/30)+'mo ago'}
function clock(ms){const t=Math.max(0,Math.round(ms/1000));return Math.floor(t/60)+':'+String(t%60).padStart(2,'0')}
function nice(ms){const t=Math.round(ms/1000),m=Math.floor(t/60);return m?`${m}m ${t%60}s`:`${t}s`}
let T=null, tick=null, discoverRun=false, cache={};

function stepState(li,s){
  const runs=(li.dataset.runs||'').split('|').filter(Boolean); if(!runs.length) return 'done';
  const idx=ORDER.indexOf(s.step), mine=runs.map(r=>ORDER.indexOf(r));
  if(!s.running) return 'done';   // between runs: show the latest results
  if(runs.includes(s.step)) return 'active';
  return Math.max(...mine)<idx?'done':'pending';
}
function setBody(id,html){if(cache[id]===html)return;cache[id]=html;document.querySelector(`#t-${id} .body`).innerHTML=html}
function setText(id,t,sub){const li=document.querySelector('#t-'+id);li.querySelector('.t').textContent=t;if(sub!==undefined)li.querySelector('.s').textContent=sub}
function cards(id,inner,label){return `<div class="cards" id="cards-${id}">${inner}</div>
  <div class="swipe"><span>${label}</span><span><button type="button" aria-label="Back" data-sc="${id}" data-d="-1">${LEFT}</button><button type="button" aria-label="Next" data-sc="${id}" data-d="1">${RIGHT}</button></span></div>`}
document.addEventListener('click',ev=>{const b=ev.target.closest('[data-sc]');if(!b)return;
  const c=document.getElementById('cards-'+b.dataset.sc);c.scrollBy({left:(+b.dataset.d)*c.clientWidth*.8,behavior:'smooth'})});

function render(s){
  const p=s.profile||{}, pr=s.prefs||{};
  // 1. read
  const first=(p.name||'').split(' ')[0];
  setText('read',first?`Read ${first}'s profile`:'Read your profile',p.headline||'');
  setBody('read',(p.orgs&&p.orgs.length?`<div class="pills">${p.orgs.map(o=>`<span class="pl org">${esc(o)}</span>`).join('')}</div>`:'')+
    (p.skills&&p.skills.length?`<div class="pills">${p.skills.map((k,i)=>`<span class="pl k${i%5+1}">${esc(k)}</span>`).join('')}</div>`:''));
  // 2. personalised
  const chips=[...(pr.titles||[]).map(t=>`<span class="pl ok">${esc(t)}</span>`),
    pr.more_titles?`<span class="pl">+${pr.more_titles} more titles</span>`:'',
    `<span class="pl ok">${esc(pr.region||'')}</span>`, pr.remote?'<span class="pl ok">remote ok</span>':''];
  setBody('prefs',`<div class="pills">${chips.join('')}</div>`);
  // 3. search
  const n=(s.total||0).toLocaleString();
  const feeds=(s.sources||[]).filter(x=>['Platsbanken','Hacker News','Arbeitnow','Web search'].includes(x.name)).length;
  const searching=document.querySelector('#t-search').classList.contains('active');
  setText('search',s.total?`${searching?'Searching':'Searched'} ${(s.boards||0).toLocaleString()} job boards, ${feeds} job feeds and the web`:'Searching job boards and the web',
    s.total?`${n} open roles read`:'company boards, Platsbanken, Hacker News, Arbeitnow and a web search');
  setBody('search',s.sources&&s.sources.length?`<div class="pills">${s.sources.map(x=>`<span class="pl">${esc(x.name)} <b>${x.n.toLocaleString()}</b></span>`).join('')}</div>`:'');
  // 4. raises
  const R=s.raises||[];
  setText('raise',R.length?`${R.length} compan${R.length>1?'ies':'y'} just raised money`:'Checking who just raised money',
    'They tend to hire next, often before the job is posted.');
  setBody('raise',R.length?cards('raise',R.map(r=>`<a class="rc" href="${r.company_id?'/companies/'+r.company_id:'#'}">
    <b>${esc(r.name)}</b><span class="amt">${esc([r.amount,r.round].filter(Boolean).join(' · '))}</span><p>${esc(r.summary)}</p>
    <span class="rl">${r.roles?r.roles+' open role'+(r.roles>1?'s':''):'No job board yet: write to them directly'}</span></a>`).join(''),'Funding rounds from the last weeks'):'');
  // 5. jobs
  const J=s.jobs||[];
  setText('jobs',s.jobs_count?`Found ${s.jobs_count} role${s.jobs_count>1?'s':''} that fit you`:'Scoring roles against your profile',
    s.jobs_count?`Each scored ${s.min_score} or more out of 10 by Claude`:'Claude reads each ad and scores it 0 to 10');
  setBody('jobs',J.length?cards('jobs',J.map(j=>`<a class="jc" href="${esc(j.url)}" target="_blank" rel="noopener" style="--tint:${tint(j.company)}">
    <div class="top"><span class="av">${esc((j.company||'?')[0].toUpperCase())}</span>${j.posted_at||j.first_seen?`<span class="age">${ago(j.posted_at||j.first_seen)}</span>`:''}</div>
    <div class="in"><span class="co">${esc(j.company)}</span><span class="ti">${esc(j.title)}</span><span class="sc">${Math.round(j.score)}/10 fit</span>
    <span class="lo">${esc(j.location||'')}</span></div></a>`).join(''),'Swipe through your matches'):
    (stepDone('jobs')?`<p class="empty-s">Nothing scored ${s.min_score}+ yet. Lavoro checks again every morning.</p>`:''));
  // 6. people
  const P=s.people||[];
  setText('people',s.people_count?`Found who to email at ${s.people_companies} compan${s.people_companies>1?'ies':'y'}`:'Finding who leads hiring',
    'The person who leads the team, not a careers inbox');
  setBody('people',P.length?`<div class="rows">${P.map(x=>`<div class="pr"><span class="av">${esc((x.company||'?')[0])}</span>
    <div><b>${esc(x.name||x.title||'Hiring contact')}</b><small>${esc([x.name?x.title:'',x.company].filter(Boolean).join(' · '))}</small></div>
    <span class="em">${esc(x.email)}<span class="trust ${esc(x.email_status)}">${esc(TRUST[x.email_status]||x.email_status)}</span></span></div>`).join('')}</div>`:
    (stepDone('people')?'<p class="empty-s">No one found yet for these roles. Big companies often hire through their careers portal.</p>':''));
  // 7. emails
  const D=s.drafts||[];
  setText('mail',s.drafts_count?`${s.drafts_count} email${s.drafts_count>1?'s':''} written`:'Writing your emails','One per role, to a real person. You read them and send them.');
  setBody('mail',D.length?`<div class="rows">${D.map(d=>`<div class="pr"><span class="av">${esc((d.company||'?')[0])}</span>
    <div><b>${esc(d.subject)}</b><small>${esc(d.company)} · to ${esc(d.to_email)}</small></div><span></span></div>`).join('')}</div>`+
    (s.drafts_count>D.length?`<p class="more">+ ${s.drafts_count-D.length} more, each to the person hiring</p>`:''):'');
}
const TRUST={listed_in_ad:'in the ad',published:'published',verified:'verified',likely:'likely',guessed:'guessed'};
function stepDone(id){return document.querySelector('#t-'+id).classList.contains('done')}

const LEFT=document.getElementById('i-left').innerHTML, RIGHT=document.getElementById('i-right').innerHTML;
function startProgress(discover){discoverRun=!!discover;document.querySelector('#t-companies').hidden=!discover;show('go');poll2()}
async function poll2(){
  try{
    const s=await (await fetch('/api/timeline')).json(); T=s;
    document.querySelectorAll('.tl>li').forEach(li=>{const st=stepState(li,s);li.classList.toggle('done',st==='done');
      li.classList.toggle('active',st==='active');li.classList.toggle('pending',st==='pending')});
    if(s.step==='Finding companies') document.querySelector('#t-companies').hidden=false;
    render(s);
    const start=s.started?new Date(s.started).getTime():Date.now();
    clearInterval(tick);
    if(s.running){
      tick=setInterval(()=>{$('#tl-time').textContent=clock(Date.now()-start)},1000);
      $('#tl-time').textContent=clock(Date.now()-start);
      return setTimeout(poll2,2500);
    }
    const end=s.finished?new Date(s.finished).getTime():Date.now();
    $('.tl-clock').classList.add('done'); $('#tl-time').textContent=s.started?'done in '+nice(end-start):'';
    $('#tl-title').textContent=!s.started?'Your latest search':s.ok?"Done. Here's what Lavoro found.":'The search stopped early.';
    $('#tl-sub').textContent=s.ok?'Your list is ready: emails to read and send, roles to apply to.':(s.last||'See output/run.log for details.');
    $('.tl-foot').classList.add('on');
  }catch(e){setTimeout(poll2,4000)}
}
if(location.hash==='#run'){show('go');poll2()}
"""


def render(cfg) -> str:
    check = icon("check")
    return f"""{head("Lavoro · Welcome")}<style>{CSS}</style></head>
<body class="welcome" data-live="1">
{scene()}
<div class="bar"><div class="wrap"><span class="brand"><span class="mark">{icon("send")}</span>Lavoro</span>
<span class="bar-right"><span class="pill quiet">Runs on your computer</span></span></div></div>
<template id="xicon">{ic("x")}</template>
<div class="dropzone" aria-hidden="true"><p>Drop your CV to start</p></div>

<main>
<section id="p-start" class="panel start on" aria-labelledby="h-start">
  <h1 id="h-start">Find the role, and <span class="em">who to write to.</span></h1>
  <p class="lede">Drop your CV. Lavoro finds roles at companies hiring now and drafts a short email to the person
  who leads the team. You read it, you send it.</p>
  <form id="startform" class="drop" autocomplete="off">
    <button class="chipbtn file" id="pick" type="button" aria-label="Choose your CV file">{ic("file")}</button>
    <button class="chipbtn link" id="paste" type="button" aria-label="Paste a portfolio link instead">{ic("link")}</button>
    <input id="source" type="text" placeholder="Portfolio link, or drop your CV" aria-label="Portfolio link or CV">
    <input id="file" type="file" accept=".pdf,.docx,.txt,.md" hidden>
    <button class="go-btn" id="go" type="submit"><span class="spin"></span>Get started{ic("arrow")}</button>
  </form>
  <div class="status-line" id="status" role="status" aria-live="polite"></div>
  <div class="err" id="err" role="alert"></div>
  <p class="hint">PDF, Word or text. On LinkedIn? Choose <b>More → Save to PDF</b> on your profile and drop that file.
  Everything stays on this computer.</p>
</section>

<section id="p-you" class="panel" aria-labelledby="hello"><div class="sheet">
  <h2 id="hello">Nice to meet you.</h2>
  <p class="sub" id="took"></p>
  <details class="read"><summary>What Lavoro took from <span id="src">your CV</span> <span id="todos"></span></summary><pre id="md"></pre></details>
  <form id="youform" class="form" autocomplete="off">
    <div class="field"><span class="lbl" id="l-titles">Roles to look for</span>
      <div class="chips" id="titles" aria-labelledby="l-titles"><input type="text" placeholder="Add a role, press Enter" aria-label="Add a role"></div>
      <div class="help">Lavoro checks job titles for these words, then Claude scores each role against your profile.</div></div>
    <div class="field"><span class="lbl" id="l-cities">Where</span>
      <div class="chips" id="cities" aria-labelledby="l-cities"><input type="text" placeholder="Add a city, press Enter" aria-label="Add a city"></div></div>
    <label class="check"><input type="checkbox" id="f-remote" checked><div><b>Remote roles in Europe are fine</b>
      <span>Also include remote roles open to Europe.</span></div></label>
    <label class="check"><input type="checkbox" id="f-sweden"><div><b>I'm looking in Sweden</b>
      <span>Adds every matching ad on Platsbanken, Sweden's public job board.</span></div></label>
    <div class="field"><label for="f-name">Your name</label><input type="text" id="f-name"><div class="help">Signs your emails.</div></div>
    <div class="two">
      <div class="field"><label for="f-portfolio">Portfolio</label><input type="url" id="f-portfolio" placeholder="https://"></div>
      <div class="field"><label for="f-linkedin">LinkedIn</label><input type="url" id="f-linkedin" placeholder="https://www.linkedin.com/in/…"></div>
    </div>
    <div class="err" id="youerr" role="alert"></div>
    <div class="actions-row"><button type="button" class="linkish" id="back">Use a different CV</button>
      <button class="go-btn" id="findbtn" type="submit"><span class="spin"></span>Find my first jobs{ic("arrow")}</button></div>
  </form>
</div></section>

<section id="p-go" class="panel" aria-labelledby="tl-title"><div class="tl-card">
  <div class="tl-head"><span class="mark">{ic("send")}</span><div><b id="tl-title">Lavoro is on it.</b>
    <small id="tl-sub">Reading job boards, scoring roles and writing to the people who hire.</small></div>
    <span class="tl-clock" aria-live="off"><i></i><span id="tl-time">0:00</span></span></div>
  <ol class="tl" aria-live="polite">
    <li id="t-read" class="done"><span class="ico c-sky">{ic("user")}</span><div><div class="t">Read your profile</div><div class="s"></div></div><span class="state">{check}</span><div class="body"></div></li>
    <li id="t-prefs" class="done"><span class="ico c-pink">{ic("sliders")}</span><div><div class="t">Personalised for you</div><div class="s">Only roles that fit you, from here on</div></div><span class="state">{check}</span><div class="body"></div></li>
    <li id="t-companies" data-runs="Finding companies" hidden><span class="ico c-ink">{ic("building")}</span><div><div class="t">Finding companies that are hiring</div><div class="s">Startups and companies with a public job board</div></div><span class="state">{check}</span><div class="body"></div></li>
    <li id="t-search" data-runs="Fetching jobs|Searching the web"><span class="ico c-amber">{ic("search")}</span><div><div class="t">Searching job boards and the web</div><div class="s"></div></div><span class="state">{check}</span><div class="body"></div></li>
    <li id="t-raise" data-runs="Checking who just raised"><span class="ico c-violet">{ic("spark")}</span><div><div class="t">Checking who just raised money</div><div class="s"></div></div><span class="state">{check}</span><div class="body"></div></li>
    <li id="t-jobs" data-runs="Scoring roles"><span class="ico c-green">{ic("brief")}</span><div><div class="t">Scoring roles against your profile</div><div class="s"></div></div><span class="state">{check}</span><div class="body"></div></li>
    <li id="t-people" data-runs="Finding people"><span class="ico c-rose">{ic("people")}</span><div><div class="t">Finding who leads hiring</div><div class="s"></div></div><span class="state">{check}</span><div class="body"></div></li>
    <li id="t-mail" data-runs="Writing emails|Finishing"><span class="ico c-red">{icon("mail")}</span><div><div class="t">Writing your emails</div><div class="s"></div></div><span class="state">{check}</span><div class="body"></div></li>
  </ol>
  <div class="tl-foot"><a class="go-btn" href="/">Open my list{ic("arrow")}</a>
    <p>Lavoro runs again every morning and adds what's new.</p></div>
  <template id="i-left">{ic("left")}</template><template id="i-right">{ic("arrow")}</template>
</div></section>
</main>
<div class="toast" role="status" aria-live="polite"></div>
<script>{BASE_JS}</script><script>{JS}</script>
</body></html>"""
