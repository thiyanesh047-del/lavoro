"""The Lavoro page.

`render()` returns the HTML. It works two ways:
  - as a file (output/latest.html, written by `build()`), where buttons copy commands for the terminal;
  - served by `python -m lavoro serve`, where buttons save straight to the database and "Find new jobs" runs the pipeline.

Look: a misty mountain valley behind everything that drifts slower than the page (parallax) and dissolves into a
soft white haze as you scroll; Instrument Serif headlines, Inter text, warm white cards, one rose action colour.
"""
from __future__ import annotations

import html
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .config import min_score as min_score_of
from .config import output_dir

STATIC = Path(__file__).resolve().parent / "static"
FONTS = ("https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1"
         "&family=Inter:wght@400;500;600;700&display=swap")

CSS = r"""
/* Soria by Bydani (see static/soria-NOTICE.txt). Missing glyphs (å, dashes, ·) fall back to Instrument Serif. */
@font-face{font-family:"Soria";src:url("assets/soria.ttf") format("truetype");font-weight:400;font-style:normal;font-display:swap}
:root{
  --canvas:#fbfaf8; --card:#ffffff; --ink:#171717; --ink-2:#3d3d3d; --mute:#666; --line:rgba(226,224,219,.95);
  --inset:#f6f5f1; --rose:#e11d48; --rose-ink:#be123c; --rose-wash:#fff1f3; --rose-glow:rgba(225,29,72,.28);
  --mint:#10b981; --mint-wash:#d1fae5; --mint-ink:#065f46; --mint-ring:rgba(110,231,183,.8);
  --amber-wash:#fef3c7; --amber-ink:#92400e; --amber-ring:rgba(252,211,77,.9);
  --serif:"Soria","Instrument Serif",Georgia,serif;
  --sans:Inter,"Inter Fallback",system-ui,-apple-system,"Segoe UI",sans-serif;
  --ease:cubic-bezier(.16,1,.3,1);
  color-scheme:light;
}
*{box-sizing:border-box}
html{background:var(--canvas);scrollbar-color:#d6d3cd transparent;scrollbar-width:thin;overflow-x:clip}
body{margin:0;color:var(--ink);font:400 15px/1.6 var(--sans);-webkit-font-smoothing:antialiased;overflow-wrap:anywhere;
  font-feature-settings:"cv11","ss01";background:transparent;min-height:100vh;display:flex;flex-direction:column}
main{flex:1 0 auto;padding-bottom:64px}
::selection{background:#ffe4e8;color:var(--ink)}
:focus-visible{outline:2px solid var(--rose);outline-offset:3px;border-radius:8px}
a{color:inherit;text-underline-offset:3px;text-decoration-thickness:1px}
code{font:500 13px/1 ui-monospace,"Cascadia Code",Consolas,monospace;background:var(--inset);border:1px solid var(--line);
  border-radius:6px;padding:2px 6px;white-space:nowrap}
.wrap{max-width:780px;margin:0 auto;padding:0 20px}

/* ---------- the valley ---------- */
.scene{position:fixed;inset:0;z-index:-1;overflow:hidden;background:#e9ece6;pointer-events:none}
.photo{position:absolute;inset:-6% -2% auto;height:112%;will-change:transform,filter}
.photo img{width:100%;height:100%;object-fit:cover;object-position:50% 38%;display:block;
  filter:saturate(.88) contrast(.94) brightness(1.05)}
/* a soft-focus copy laid over the sharp one gives the dreamy bloom */
.photo .bloom{position:absolute;inset:0;mix-blend-mode:screen;opacity:.42;filter:blur(14px) saturate(1.1) brightness(1.08)}
.haze{position:absolute;inset:0;background:
  radial-gradient(70% 45% at 50% 0%,rgba(255,250,246,.55),transparent 70%),
  linear-gradient(180deg,rgba(255,255,255,.18) 0%,rgba(255,255,255,0) 30%,rgba(251,250,248,.15) 60%,rgba(251,250,248,.55) 100%)}
.mist{position:absolute;left:-30%;width:160%;height:38%;border-radius:50%;filter:blur(40px);opacity:.55;
  background:radial-gradient(50% 50% at 50% 50%,rgba(255,255,255,.95),rgba(255,255,255,0) 70%);will-change:transform}
.mist.m1{top:38%;animation:drift 70s ease-in-out infinite alternate}
.mist.m2{top:62%;height:30%;opacity:.45;animation:drift 95s ease-in-out infinite alternate-reverse}
@keyframes drift{from{transform:translateX(-6%)}to{transform:translateX(6%)}}
.veil{position:absolute;inset:0;background:var(--canvas);opacity:0;will-change:opacity}

/* ---------- top bar ---------- */
.bar{position:sticky;top:0;z-index:5;transition:background .4s,border-color .4s,backdrop-filter .4s;border-bottom:1px solid transparent}
.bar.scrolled{background:rgba(251,250,248,.82);backdrop-filter:saturate(1.4) blur(12px);border-bottom-color:var(--line)}
.bar .wrap{display:flex;align-items:center;justify-content:space-between;height:64px;gap:12px}
.brand{display:flex;align-items:center;gap:10px;white-space:nowrap;font:400 25px/1 var(--serif);letter-spacing:-.01em;text-decoration:none}
.mark{width:30px;height:30px;border-radius:9px;background:var(--rose);color:#fff;display:grid;place-items:center;
  box-shadow:0 4px 10px -2px var(--rose-glow)}
.mark svg{width:16px;height:16px}
.bar-right{display:flex;gap:8px;align-items:center}
.pill{display:inline-flex;align-items:center;gap:8px;min-height:36px;padding:0 14px;border-radius:999px;
  background:var(--mint-wash);color:var(--mint-ink);font:600 13.5px/1 var(--sans);box-shadow:0 0 0 1px var(--mint-ring) inset;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.pill.quiet{background:rgba(255,255,255,.75);color:var(--ink-2);box-shadow:0 0 0 1px var(--line) inset}
.run{border:0;cursor:pointer;background:var(--ink);color:#fff;min-height:36px;padding:0 16px;border-radius:999px;
  font:600 13.5px/1 var(--sans);display:none;align-items:center;gap:8px;transition:background .2s}
.live .run{display:inline-flex}
.run:hover{background:#333}.run[disabled]{opacity:.7;cursor:progress}
.run svg{width:15px;height:15px}.run.busy svg{animation:spin 1.1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* ---------- hero over the photo ---------- */
header.hero{min-height:min(78vh,720px);display:flex;align-items:flex-start;padding:9vh 0 48px}
h1{font:400 clamp(44px,7.4vw,76px)/1.02 var(--serif);letter-spacing:-.025em;margin:0;max-width:15ch;text-wrap:balance;
  text-shadow:0 1px 30px rgba(255,252,248,.85),0 0 2px rgba(255,252,248,.6)}
h1 .em{text-decoration:underline wavy #f43f5e;text-decoration-thickness:2px;text-underline-offset:12px;text-decoration-skip-ink:none}
.glass{margin-top:22px;display:inline-block;max-width:560px;padding:16px 18px;border-radius:16px;
  background:rgba(255,253,250,.72);backdrop-filter:blur(14px) saturate(1.2);box-shadow:0 0 0 1px rgba(255,255,255,.7) inset,
  0 12px 40px -18px rgba(40,50,40,.35)}
.lede{margin:0;font:500 16.5px/1.6 var(--sans);color:#222}
.meta-row{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px;margin-top:12px;color:#4a4a4a;font-size:13.5px;
  font-variant-numeric:tabular-nums}
.meta-row b{color:var(--ink);font-weight:600}
.dot{width:7px;height:7px;border-radius:50%;background:var(--mint);display:inline-block;margin-right:6px;box-shadow:0 0 0 3px rgba(16,185,129,.16)}
.sep{color:#b9b5ad}
.region{display:flex;align-items:center;flex-wrap:wrap;gap:8px 10px;margin-top:12px;padding-top:12px;border-top:1px solid rgba(0,0,0,.07);
  font:500 13.5px var(--sans);color:#3a3a3a}
.region select{font:600 13.5px var(--sans);color:var(--ink);height:34px;padding:0 30px 0 12px;border-radius:999px;border:0;
  background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23666' stroke-width='2.5'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") no-repeat right 11px center;
  -webkit-appearance:none;appearance:none;box-shadow:0 0 0 1px var(--line) inset;cursor:pointer}
.region-note{color:var(--mute);font-size:12.5px}


/* ---------- content rises out of the haze ---------- */
main{position:relative}
main::before{content:"";position:absolute;z-index:-1;left:-50vw;right:-50vw;top:-140px;bottom:0;
  background:linear-gradient(180deg,rgba(251,250,248,0) 0,rgba(251,250,248,.85) 140px,var(--canvas) 260px)}
section{padding:8px 0}
h2{font:400 34px/1.1 var(--serif);margin:36px 0 6px;letter-spacing:-.015em}
.sub{margin:0 0 16px;color:var(--mute);font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:0 1px 2px rgba(16,16,16,.04)}

.job{padding:24px;margin:0 0 16px;transition:opacity .45s var(--ease),transform .45s var(--ease)}
.job.leaving{opacity:0;transform:translateY(-8px) scale(.99)}
.job-head{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:start}
.job-title{margin:0;font:600 17px/1.35 var(--sans);letter-spacing:-.01em}
.job-title a{text-decoration:none}.job-title a:hover{text-decoration:underline}
.job-meta{margin-top:4px;color:var(--mute);font-size:14px}
.fit{text-align:right;line-height:1}
.fit .n{font:400 44px/.9 var(--serif);letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.fit .of{display:block;margin-top:6px;color:var(--mute);font-size:12px;white-space:nowrap}
.why{margin:14px 0 0;color:var(--ink-2);font-size:14.5px;max-width:68ch}
.to{display:flex;gap:12px;align-items:flex-start;margin-top:18px;padding:12px 14px;border-radius:12px;background:var(--inset)}
.avatar{flex:none;width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#fff;
  box-shadow:0 0 0 1px var(--line) inset;font:400 18px/1 var(--serif);color:var(--ink-2)}
.to-main{min-width:0;flex:1}
.to-name{font-weight:600;font-size:14.5px}.to-name span{font-weight:400;color:var(--mute)}
.to-mail{font-size:13.5px;color:var(--ink-2);display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;margin-top:2px}
.trust{display:inline-flex;align-items:center;height:22px;padding:0 9px;border-radius:999px;font:600 11.5px/1 var(--sans)}
.trust.listed_in_ad,.trust.published,.trust.verified{background:var(--mint-wash);color:var(--mint-ink);box-shadow:0 0 0 1px var(--mint-ring) inset}
.trust.likely{background:var(--amber-wash);color:var(--amber-ink);box-shadow:0 0 0 1px var(--amber-ring) inset}
.trust.guessed,.trust.none{background:var(--rose-wash);color:var(--rose-ink);box-shadow:0 0 0 1px rgba(253,164,175,.9) inset}
.via{color:var(--mute);font-size:12.5px}
.note{margin-top:6px;color:var(--mute);font-size:12.5px}
.note summary{cursor:pointer;color:var(--ink-2);font-weight:500;width:max-content}
.note p{margin:6px 0 0;max-width:62ch}
.letter{margin-top:16px;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.subject{padding:12px 16px;border-bottom:1px solid var(--line);font-weight:600;font-size:14.5px;display:flex;gap:10px}
.subject small{flex:none;color:var(--mute);font-weight:500;white-space:nowrap;overflow-wrap:normal}
.body{margin:0;padding:16px;white-space:pre-wrap;font:400 14.5px/1.7 var(--sans);color:#262626;max-height:340px;overflow:auto}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px;align-items:center}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:0 18px;border-radius:999px;
  border:0;font:600 14.5px/1 var(--sans);cursor:pointer;text-decoration:none;color:var(--ink);background:#fff;
  box-shadow:0 0 0 1px var(--line) inset,0 1px 2px rgba(16,16,16,.04);transition:transform .15s,box-shadow .2s,background .2s}
.btn svg{width:16px;height:16px;flex:none}
.btn:hover{background:#f6f5f2}.btn:active{transform:translateY(1px)}
.btn.go{background:var(--rose);color:#fff;border-radius:14px;padding:0 20px;box-shadow:0 10px 24px -6px var(--rose-glow)}
.btn.go:hover{background:var(--rose-ink);box-shadow:0 12px 28px -6px rgba(225,29,72,.38)}
.btn.done{background:var(--mint-wash);color:var(--mint-ink);box-shadow:0 0 0 1px var(--mint-ring) inset}
.btn.text{background:transparent;box-shadow:none;color:var(--mute);padding:0 10px}
.btn.text:hover{color:var(--ink);background:transparent}
.spacer{flex:1}
.job.is-sent{opacity:.6}
.job.is-sent .letter,.job.is-sent .why{display:none}

.list{overflow:hidden}
.row{display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 18px;border-top:1px solid var(--line);
  text-decoration:none;transition:background .2s}
.row:first-child{border-top:0}
a.row:hover{background:#fcfbf9}
.row-title{font-weight:600;font-size:15px}
.row-meta{color:var(--mute);font-size:13.5px;margin-top:1px}
.row-why{color:var(--ink-2);font-size:13.5px;margin-top:6px;max-width:64ch}
.row-side{text-align:right;color:var(--mute);font-size:12.5px;white-space:nowrap}
.row-side .n{display:block;font:400 28px/1 var(--serif);color:var(--ink);font-variant-numeric:tabular-nums}
/* Shared job line (browse.job_row), used on Today and the browse pages */
.jrow{display:grid;grid-template-columns:1fr auto;gap:16px;align-items:center;padding:14px 18px;border-top:1px solid var(--line)}
.jrow:first-child{border-top:0}
.jrow:hover{background:#fcfbf9}
.jt{font-weight:600;font-size:15px;text-decoration:none}.jt:hover{text-decoration:underline}
.jm{color:var(--mute);font-size:13.5px;margin-top:2px}
.jm a{color:var(--ink-2);text-decoration:none;font-weight:500}.jm a:hover{text-decoration:underline}
.side{text-align:right;color:var(--mute);font-size:12.5px;white-space:nowrap;display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.side .n{font:400 26px/1 var(--serif);color:var(--ink);font-variant-numeric:tabular-nums}
.tag{display:inline-flex;align-items:center;height:22px;padding:0 9px;border-radius:999px;font:600 11.5px/1 var(--sans)}
.tag.ready{background:var(--mint-wash);color:var(--mint-ink);box-shadow:0 0 0 1px var(--mint-ring) inset;text-decoration:none}
.tag.pay{background:#f3f1ec;color:var(--ink-2)}
details.more>summary{list-style:none;cursor:pointer;display:inline-flex;align-items:center;gap:10px;margin:36px 0 6px;
  font:400 34px/1.1 var(--serif);letter-spacing:-.015em}
details.more>summary::-webkit-details-marker{display:none}
details.more>summary svg{width:20px;height:20px;transition:transform .35s var(--ease);color:var(--mute)}
details.more[open]>summary svg{transform:rotate(90deg)}

.empty{padding:28px 24px}
.empty h3{margin:0 0 6px;font:400 28px/1.1 var(--serif);letter-spacing:-.01em}
.empty p{margin:0;color:var(--ink-2);max-width:60ch}

footer{margin:0;padding:22px 0 40px;border-top:1px solid var(--line);color:var(--mute);font-size:13px;background:var(--canvas)}
footer .wrap{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 20px}

.toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,16px);opacity:0;pointer-events:none;z-index:9;
  background:var(--ink);color:#fff;padding:12px 16px;border-radius:12px;font:500 14px/1.4 var(--sans);max-width:calc(100% - 32px);
  box-shadow:0 12px 32px -8px rgba(0,0,0,.35);transition:opacity .3s,transform .4s var(--ease)}
.toast.on{opacity:1;transform:translate(-50%,0)}

@media (max-width:640px){
  header.hero{min-height:82vh;padding-top:6vh}
  .glass{padding:14px}
  .lede{font-size:15.5px}
  .meta-row{flex-direction:column;align-items:flex-start;gap:2px}
  .meta-row .sep{display:none}
  .job{padding:18px}
  .fit .n{font-size:34px}
  .actions .btn{flex:1 1 auto}
  .actions .btn.go{flex-basis:100%}
  .spacer{display:none}
  .bar .pill.quiet{display:none}
  .run{padding:0 11px}.run span{display:none}
  .row,.jrow{padding:14px}
  h2,details.more>summary{font-size:30px}
}
.bar .wrap{max-width:1080px}
.nav{display:flex;gap:2px;margin:0 auto 0 20px}
.nav a{padding:8px 13px;border-radius:999px;font:500 14.5px/1 var(--sans);text-decoration:none;color:var(--ink-2);white-space:nowrap;
  transition:background .2s,color .2s}
.nav a:hover{background:rgba(255,255,255,.65);color:var(--ink)}
.nav a[aria-current=page]{background:#fff;color:var(--ink);box-shadow:0 0 0 1px var(--line) inset}
@media (max-width:900px){.bar .pill.quiet{display:none}}
@media (max-width:640px){
  .bar .wrap{flex-wrap:wrap;height:auto;padding-top:10px;padding-bottom:8px;row-gap:8px}
  .nav{order:3;width:100%;margin:0;overflow-x:auto}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

JS = r"""
const LIVE = location.protocol.startsWith('http') && document.body.dataset.live === '1';
if (LIVE) document.body.classList.add('live');
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

/* valley: drifts slower than the page, softens and fades into the haze */
const photo=document.querySelector('.photo'), veil=document.querySelector('.veil'), bar=document.querySelector('.bar');
let ticking=false;
function paint(){
  const y=scrollY, h=innerHeight, t=Math.min(y/(h*1.1),1);
  if(!reduce){photo.style.transform=`translate3d(0,${-y*0.22}px,0) scale(${1+t*0.06})`;
    photo.style.filter=`blur(${(t*5).toFixed(2)}px)`;}
  veil.style.opacity=(Math.max(0,(y-h*0.35)/(h*0.9))*0.92).toFixed(3);
  bar.classList.toggle('scrolled',y>8); ticking=false;
}
addEventListener('scroll',()=>{if(!ticking){ticking=true;requestAnimationFrame(paint)}},{passive:true});
addEventListener('resize',paint); paint();

const toast=document.querySelector('.toast');let tt;
function say(t){toast.textContent=t;toast.classList.add('on');clearTimeout(tt);tt=setTimeout(()=>toast.classList.remove('on'),2800)}
async function copy(t){try{await navigator.clipboard.writeText(t);return true}catch(e){
  const a=document.createElement('textarea');a.value=t;document.body.appendChild(a);a.select();
  let ok=false;try{ok=document.execCommand('copy')}catch(_){}a.remove();return ok}}
const store={get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{v?localStorage.setItem(k,v):localStorage.removeItem(k)}catch(e){}}};
async function api(path,body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},
  body:body?JSON.stringify(body):undefined});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||r.statusText);return d}

document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{
  const card=b.closest('.job');const text='Subject: '+card.dataset.subject+'\n\n'+card.querySelector('.body').innerText;
  say(await copy(text)?'Email copied. Paste it into Gmail.':'Could not copy. Select the text instead.')}));

function paintSent(card,on){card.classList.toggle('is-sent',on);const b=card.querySelector('[data-sent]');
  b.classList.toggle('done',on);b.querySelector('span').textContent=on?'Sent':'Mark as sent'}
document.querySelectorAll('.job').forEach(card=>{
  const key=card.dataset.key;
  if(!LIVE) paintSent(card,store.get('sent:'+key)==='1');
  card.querySelector('[data-sent]').addEventListener('click',async()=>{
    const on=!card.classList.contains('is-sent');
    if(LIVE){try{await api('/api/mark',{key,status:on?'sent':'drafted'});paintSent(card,on);say(on?'Saved as sent.':'Moved back to ready.')}
      catch(e){say('Could not save: '+e.message)}return}
    store.set('sent:'+key,on?'1':null);paintSent(card,on);
    if(on){const cmd='python -m lavoro mark '+key+' sent';
      say(await copy(cmd)?'Marked here. The save command is copied: paste it in your terminal.':'Marked here. Run: '+cmd)}
  });
  card.querySelector('[data-skip]').addEventListener('click',async()=>{
    if(LIVE){try{await api('/api/mark',{key,status:'skipped'})}catch(e){say('Could not save: '+e.message);return}}
    else{store.set('sent:'+key,null);const cmd='python -m lavoro mark '+key+' skipped';await copy(cmd)}
    card.classList.add('leaving');setTimeout(()=>card.remove(),450);
    say(LIVE?'Skipped. It won\'t come back.':'Hidden. The skip command is copied for your terminal.')
  });
});

const regionSel=document.getElementById('region');
if(regionSel)regionSel.addEventListener('change',async()=>{try{
  const r=await api('/api/region',{region:regionSel.value});
  say(`Searching ${r.label} from the next run. ${r.reopened?r.reopened.toLocaleString()+' earlier roles will be checked again.':''}`)}
  catch(e){say('Could not save: '+e.message)}});

/* live mode: run the pipeline from the page */
const runBtn=document.querySelector('.run');
async function poll(){try{const s=await api('/api/status');
  if(s.running){runBtn.disabled=true;runBtn.classList.add('busy');runBtn.querySelector('span').textContent=s.step||'Working';setTimeout(poll,2500)}
  else if(runBtn.classList.contains('busy')){say(s.ok?'Done. Loading the new list.':'The run stopped: '+(s.last||'see output/run.log'));
    setTimeout(()=>location.reload(),s.ok?900:4000)}}catch(e){setTimeout(poll,5000)}}
if(LIVE&&runBtn){runBtn.addEventListener('click',async()=>{try{await api('/api/run',{});location.href='/welcome#run'}
  catch(e){if(/already running/i.test(e.message))location.href='/welcome#run';else say(e.message)}});poll()}
"""

ICON = {
    "send": '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>',
    "mail": '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "chev": '<path d="m9 18 6-6-6-6"/>',
    "refresh": '<path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/>',
}


def icon(name: str) -> str:
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true">{ICON[name]}</svg>')


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


TRUST_LABEL = {"listed_in_ad": "Listed in the ad", "published": "Published online", "verified": "Verified", "likely": "Likely", "guessed": "Guessed, check first",
               "none": "No email"}
SOURCE_LABEL = {"ad": "the job ad", "web_search": "web search", "hunter": "Hunter", "pattern": "email pattern"}


def ago(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00").replace(" UTC", "+00:00"))
    except ValueError:
        return ts[:10]
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc).date() - d.astimezone(timezone.utc).date()).days
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago" if days < 30 else d.strftime("%d %b")


def initials(name: str | None) -> str:
    parts = [p for p in (name or "").split() if p[:1].isalpha()]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "@"


def meta_line(j) -> str:
    return " · ".join(e(b) for b in [j["company"], j["location"], j["salary"]] if b)


def row(j, show_why=False) -> str:
    why = f'<div class="row-why">{e(j["score_reason"])}</div>' if show_why and j["score_reason"] else ""
    return (f'<a class="row" href="{e(j["url"])}" target="_blank" rel="noopener"><div>'
            f'<div class="row-title">{e(j["title"])}</div><div class="row-meta">{meta_line(j)}</div>{why}</div>'
            f'<div class="row-side"><span class="n">{int(j["score"] or 0)}</span>{e(ago(j["posted_at"]))}</div></a>')


def _job_card(j) -> str:
    status = j["email_status"] or "none"
    gmail = ("https://mail.google.com/mail/?view=cm&fs=1&to=" + quote(j["to_email"] or "") +
             "&su=" + quote(j["subject"] or "") + "&body=" + quote(j["body"] or ""))
    mailto = f"mailto:{quote(j['to_email'] or '')}?subject={quote(j['subject'] or '')}&body={quote(j['body'] or '')}"
    via = e(SOURCE_LABEL.get(j["c_source"], j["c_source"] or ""))
    if j["source_url"]:
        via = f'<a href="{e(j["source_url"])}" target="_blank" rel="noopener">{via}</a>'
    role = f' <span>· {e(j["c_title"])}</span>' if j["c_title"] else ""
    posted = ago(j["posted_at"])
    return f"""<article class="card job" data-key="{e(j['key'])}" data-subject="{e(j['subject'])}">
<div class="job-head"><div><h3 class="job-title"><a href="{e(j['url'])}" target="_blank" rel="noopener">{e(j['title'])}</a></h3>
<div class="job-meta">{meta_line(j)}{(' · posted ' + e(posted)) if posted else ''}</div></div>
<div class="fit" title="How well this role fits your profile"><span class="n">{int(j['score'] or 0)}</span><span class="of">of 10 fit</span></div></div>
{f'<p class="why">{e(j["score_reason"])}</p>' if j["score_reason"] else ''}
<div class="to"><span class="avatar">{e(initials(j['c_name']))}</span><div class="to-main">
<div class="to-name">{e(j['c_name'] or 'Hiring inbox')}{role}</div>
<div class="to-mail">{e(j['to_email'])}<span class="trust {e(status)}">{e(TRUST_LABEL.get(status, status))}</span>
<span class="via">found via {via}</span></div>{f'<details class="note"><summary>Why this person</summary><p>{e(j["note"])}</p></details>' if j["note"] else ''}</div></div>
<div class="letter"><div class="subject"><small>Subject</small>{e(j['subject'])}</div><pre class="body">{e(j['body'])}</pre></div>
<div class="actions"><a class="btn go" href="{e(gmail)}" target="_blank" rel="noopener">{icon('mail')}Open in Gmail</a>
<a class="btn" href="{e(mailto)}">Mail app</a><button class="btn" type="button" data-copy>{icon('copy')}Copy</button>
<button class="btn" type="button" data-sent>{icon('check')}<span>Mark as sent</span></button>
<span class="spacer"></span><button class="btn text" type="button" data-skip>Not for me</button>
{'<span class="via">Also in Gmail Drafts</span>' if j['gmail_draft_id'] else ''}</div>
</article>"""


def head(title: str, live: bool = True) -> str:
    # Live pages sit at nested paths (/roles/x, /companies/2); a base URL keeps assets/… pointing at /assets/.
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">{'<base href="/">' if live else ''}
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}"><link rel="preload" as="image" href="{asset('valley-wide.webp')}">
<link rel="preload" as="font" type="font/ttf" href="assets/soria.ttf" crossorigin><style>{CSS}</style>"""


def asset(name: str) -> str:
    """URL for a static file, versioned by its modified time so browsers never keep an old copy."""
    f = STATIC / name
    return f"assets/{name}?v={int(f.stat().st_mtime)}" if f.exists() else f"assets/{name}"


def scene() -> str:
    w, t = asset("valley-wide.webp"), asset("valley-tall.webp")
    return f"""<div class="scene" aria-hidden="true"><div class="photo"><picture>
<source media="(max-aspect-ratio: 4/5)" srcset="{t}"><img src="{w}" alt=""></picture>
<picture class="bloom"><source media="(max-aspect-ratio: 4/5)" srcset="{t}">
<img src="{w}" alt="" style="width:100%;height:100%;object-fit:cover;object-position:50% 38%"></picture></div>
<div class="haze"></div><div class="mist m1"></div><div class="mist m2"></div><div class="veil"></div></div>"""



NAV = [("/", "Today"), ("/jobs", "All jobs"), ("/roles", "Roles"), ("/companies", "Companies"), ("/tracker", "Tracker")]


def bar(active: str | None, right: str = "") -> str:
    """Top bar. `active` is the current nav path; None hides the nav (static file, no server to link to)."""
    nav = ""
    if active is not None:
        nav = '<nav class="nav" aria-label="Main">' + "".join(
            f'<a href="{href}"{' aria-current="page"' if href == active else ''}>{label}</a>' for href, label in NAV) + "</nav>"
    brand = f'<a class="brand" href="/"><span class="mark">{icon("send")}</span>Lavoro</a>' if active is not None else         f'<span class="brand"><span class="mark">{icon("send")}</span>Lavoro</span>'
    return f'<div class="bar"><div class="wrap">{brand}{nav}<span class="bar-right">{right}</span></div></div>'


def render(con, cfg, live: bool = False) -> str:
    min_score = min_score_of(cfg)
    today = date.today()
    ready = con.execute(
        """SELECT j.*, d.subject, d.body, d.to_email, d.gmail_draft_id, c.name AS c_name, c.title AS c_title,
                  c.email_status, c.source AS c_source, c.source_url, c.note
           FROM drafts d JOIN jobs j ON j.key=d.job_key LEFT JOIN contacts c ON c.id=d.contact_id
           WHERE j.status='drafted' ORDER BY j.score DESC, j.first_seen DESC""").fetchall()
    nocontact = con.execute("SELECT * FROM jobs WHERE status='no_contact' ORDER BY score DESC, first_seen DESC LIMIT 40").fetchall()
    others = con.execute(
        "SELECT * FROM jobs WHERE status='scored' AND score < ? AND date(first_seen) >= date('now','-7 day') "
        "ORDER BY score DESC LIMIT 60", (min_score,)).fetchall()
    q = lambda sql: con.execute(sql).fetchone()[0]
    new_today = q("SELECT count(*) FROM jobs WHERE date(first_seen)=date('now')")
    passed = q("SELECT count(*) FROM jobs WHERE passed_filter=1 AND date(first_seen)>=date('now','-7 day')")
    sent = q("SELECT count(*) FROM jobs WHERE status='sent'")
    boards = q("SELECT count(*) FROM companies WHERE ats IS NOT NULL AND ats<>'none'")
    n = len(ready)

    hour = datetime.now().hour
    hello = "Good morning." if hour < 12 else "Good afternoon." if hour < 18 else "Good evening."
    if n:
        headline = f'{hello} <span class="em">{n} {"email is" if n == 1 else "emails are"}</span> ready.'
        lede = "Each one goes to a real person at a company that is hiring now. Read it, change what you like, and send it from your own Gmail."
    else:
        headline = f"{hello} Nothing to send yet."
        lede = "No new job cleared your bar with a contact attached. The lists below show what came close."

    from . import regions as _regions
    cur_region = _regions.current(cfg)
    region_html = ""
    if live:
        opts = "".join(f'<option value="{k}"{" selected" if k == cur_region else ""}>{e(v)}</option>' for k, v in _regions.LABELS.items())
        region_html = (f'<label class="region">Searching in <select id="region" aria-label="Search region">{opts}</select>'
                       f'<span class="region-note">The daily run uses this.</span></label>')
    out = [f"""{head(f"Lavoro · {today:%d %b}", live)}</head>
<body data-live="{1 if live else 0}">
{scene()}
{bar("/" if live else None, f'<span class="pill quiet">{today:%A %d %B}</span><span class="pill"><span class="dot" style="margin-right:0"></span>{n} ready</span><button class="run" type="button" aria-label="Find new jobs">{icon("refresh")}<span>Find new jobs</span></button>')}
<header class="hero"><div class="wrap"><h1>{headline}</h1>
<div class="glass"><p class="lede">{lede}</p>
<div class="meta-row"><span><span class="dot"></span><b>{new_today:,}</b> new roles today</span><span class="sep">·</span>
<span><b>{passed}</b> matched your filters this week</span><span class="sep">·</span>
<span><b>{boards}</b> company boards watched</span><span class="sep">·</span><span><b>{sent}</b> sent so far</span></div>
{region_html}</div>
</div></header><main><div class="wrap">"""]

    out.append('<section><h2>Ready to send</h2><p class="sub">Best fit first. Check every address marked anything other than green.</p>')
    if not ready:
        out.append('<div class="card empty"><h3>All caught up.</h3><p>'
                   + ("Press <b>Find new jobs</b> above for a fresh search" if live else "Run <code>python -m lavoro run</code> for a fresh search")
                   + ', or lower <code>min_score</code> in <code>config.yaml</code> to see more.</p></div>')
    out.extend(_job_card(j) for j in ready)
    out.append("</section>")

    followed = con.execute("SELECT count(*) FROM companies WHERE starred=1").fetchone()[0]
    fresh = con.execute(
        """SELECT j.*, c.id AS cid FROM jobs j JOIN companies c ON c.id=j.company_id
           WHERE c.starred=1 AND j.status NOT IN ('closed','duplicate') AND substr(coalesce(j.posted_at, j.first_seen), 1, 10) >= date('now','-7 day')
           ORDER BY substr(coalesce(j.posted_at, j.first_seen), 1, 10) DESC, j.first_seen DESC LIMIT 30""").fetchall()
    fresh_total = con.execute(
        """SELECT count(*) FROM jobs j JOIN companies c ON c.id=j.company_id
           WHERE c.starred=1 AND j.status NOT IN ('closed','duplicate') AND substr(coalesce(j.posted_at, j.first_seen), 1, 10) >= date('now','-7 day')""").fetchone()[0]
    if live:  # follow-ups from the tracker that are due today
        from .tracker import due
        rows_due = due(con)
        if rows_due:
            items = "".join(
                f'<a class="row" href="/tracker"><div><div class="row-title">Follow up with {e(r["company"])}</div>'
                f'<div class="row-meta">{e(r["title"] or "")}{" · " + e(r["email"]) if r["email"] else ""}</div></div>'
                f'<div class="row-side">due {e(r["follow_up"])}</div></a>' for r in rows_due[:6])
            out.append(f'<section><h2>Follow up today</h2><p class="lede" style="margin:0 0 14px;color:var(--ink-2)">'
                       f'{len(rows_due)} role{"s" if len(rows_due) != 1 else ""} from your tracker waiting a week or more.</p>'
                       f'<div class="card list">{items}</div></section>')
    if followed or live:
        from .browse import job_row
        out.append('<section><h2>New at companies you follow</h2>')
        if fresh:
            shown = f" The newest {len(fresh)} are below." if fresh_total > len(fresh) else ""
            out.append(f'<p class="sub">{fresh_total} role{"s" if fresh_total != 1 else ""} posted in the last 7 days at the '
                       f'{followed} compan{"ies" if followed != 1 else "y"} you follow, any title.{shown}</p>'
                       f'<div class="card list">{"".join(job_row(r) for r in fresh)}</div>')
        elif followed:
            out.append(f'<div class="card empty"><p>Nothing new this week at the {followed} compan{"ies" if followed != 1 else "y"} you follow.</p></div>')
        else:
            out.append('<div class="card empty"><p>Follow companies on the <a href="/companies">Companies</a> page with the star. '
                       'Every new role they post shows up here, whatever the title.</p></div>')
        out.append("</section>")

    out.append(f'<section><h2>Good fit, no email found</h2><p class="sub">'
               f'{len(nocontact)} roles cleared your bar but no address turned up. Apply through the link, or find the team lead yourself.</p>')
    out.append(f'<div class="card list">{"".join(row(j) for j in nocontact)}</div>' if nocontact
               else '<div class="card empty"><p>None today.</p></div>')
    out.append("</section>")

    out.append(f'<section><details class="more"><summary>{icon("chev")}Close, but below {e(min_score)}</summary>'
               f'<p class="sub">{len(others)} roles from the last 7 days, with the reason each fell short.</p>')
    out.append(f'<div class="card list">{"".join(row(j, show_why=True) for j in others)}</div>' if others
               else '<div class="card empty"><p>None this week.</p></div>')
    out.append("</details></section></div></main>")

    out.append(f"""<footer><div class="wrap"><span>Lavoro · built {datetime.now():%H:%M} from your local database</span>
<span>Nothing here is sent until you send it.{' · <a href="/welcome">Set up again</a>' if live else ''}</span></div></footer>
<div class="toast" role="status" aria-live="polite"></div><script>{JS}</script></body></html>""")
    return "\n".join(out)


def copy_assets(dest: Path) -> None:
    (dest / "assets").mkdir(parents=True, exist_ok=True)
    for f in STATIC.iterdir():
        t = dest / "assets" / f.name
        if not t.exists() or t.stat().st_mtime < f.stat().st_mtime:
            shutil.copy2(f, t)


def build(con, cfg) -> str:
    d = output_dir(cfg)
    copy_assets(d)
    page = render(con, cfg, live=False)
    (d / f"digest-{date.today().isoformat()}.html").write_text(page, encoding="utf-8")
    (d / "latest.html").write_text(page, encoding="utf-8")
    return str(d / "latest.html")
