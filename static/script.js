let chart = null;

const $ = id => document.getElementById(id);
const show = (id, yes=true) => $(id)?.classList.toggle("hidden", !yes);
function toast(msg){const el=$("toast");el.textContent=msg;el.classList.add("show");setTimeout(()=>el.classList.remove("show"),2400)}
function money(v){return v == null ? "—" : "₹" + Number(v).toLocaleString("en-IN",{maximumFractionDigits:2})}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}

async function analyze(ticker){
  ticker=(ticker||"").trim().toUpperCase();
  if(!ticker)return;
  $("tickerInput").value=ticker;
  show("loading",true);show("errorBox",false);
  try{
    const res=await fetch(`/api/predict?ticker=${encodeURIComponent(ticker)}`);
    const data=await res.json();
    if(!res.ok||!data.success)throw new Error(data.error||"Analysis failed");
    $("lastClose").textContent=money(data.last_close);
    $("lastDate").textContent=`As of ${data.last_date}`;
    $("signal").textContent=data.predicted_direction;
    $("signal").className=data.predicted_direction==="UP"?"profit":"loss";
    $("confidence").textContent=`Confidence ${data.confidence}%`;
    $("accuracy").textContent=data.metrics?.test_accuracy!=null?`${(data.metrics.test_accuracy*100).toFixed(1)}%`:"—";
    $("volatility").textContent=data.indicators?.volatility!=null?`${data.indicators.volatility}%`:"—";
    $("tickerBadge").textContent=data.ticker||ticker;
    $("chartTitle").textContent=`${ticker} · last 60 sessions`;
    $("rsi").textContent=data.indicators?.rsi_14??"—";
    $("macd").textContent=data.indicators?.macd??"—";
    $("macdSignal").textContent=data.indicators?.macd_signal??"—";
    $("sma20").textContent=money(data.indicators?.sma_20);
    $("ema10").textContent=money(data.indicators?.ema_10);
    drawChart(data.prices||[]);
    toast(`${ticker} analysis ready`);
  }catch(e){
    $("errorBox").textContent=e.message;
    show("errorBox",true);
  }finally{show("loading",false)}
}

function drawChart(points){
  const ctx=$("priceChart");
  if(chart)chart.destroy();
  chart=new Chart(ctx,{type:"line",data:{labels:points.map(p=>p.date),datasets:[{data:points.map(p=>p.close),borderColor:"#38bdf8",backgroundColor:"rgba(56,189,248,.08)",fill:true,tension:.25,pointRadius:0,borderWidth:2}]},
  options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:"#71869b",maxTicksLimit:7},grid:{display:false}},y:{ticks:{color:"#71869b"},grid:{color:"rgba(255,255,255,.06)"}}}}});
}

async function loadWatchlist(){
  const res=await fetch("/api/watchlist"); if(!res.ok)return;
  const data=await res.json(); const grid=$("watchlistGrid");
  if(!data.items.length){grid.innerHTML='<div class="muted">No saved stocks yet. Search a stock and click ☆.</div>';return}
  grid.innerHTML=data.items.map(t=>`<div class="watch-card"><strong>${escapeHtml(t)}</strong><div class="muted" id="q-${CSS.escape(t)}">Loading…</div><div class="watch-actions"><button class="small-btn" onclick="analyze('${escapeHtml(t)}')">Analyze</button><button class="small-btn" onclick="removeWatch('${escapeHtml(t)}')">Remove</button></div></div>`).join("");
  for(const t of data.items){
    try{const q=await (await fetch(`/api/quote?ticker=${encodeURIComponent(t)}`)).json();const el=document.querySelector(`#q-${CSS.escape(t)}`);if(el&&q.success)el.innerHTML=`${money(q.last_close)} <span class="${q.change_pct>=0?'profit':'loss'}">${q.change_pct>=0?'+':''}${q.change_pct}%</span>`}catch{}
  }
}
async function addWatch(){
  const ticker=$("tickerInput").value.trim().toUpperCase(); if(!ticker)return;
  const res=await fetch("/api/watchlist",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ticker})});
  const d=await res.json(); if(!d.success)return toast(d.error||"Could not save");
  toast(`${ticker} added to watchlist`);loadWatchlist();
}
async function removeWatch(ticker){
  await fetch(`/api/watchlist/${encodeURIComponent(ticker)}`,{method:"DELETE"});loadWatchlist();toast("Removed");
}

async function loadPortfolio(){
  const d=await (await fetch("/api/portfolio")).json(); if(!d.success)return;
  $("portfolioValue").textContent=money(d.total_value);$("portfolioCost").textContent=money(d.total_cost);$("portfolioPnl").textContent=money(d.total_pnl);
  $("portfolioPnl").className=d.total_pnl>=0?"profit":"loss";
  const box=$("portfolioTable");
  if(!d.items.length){box.innerHTML='<div class="muted">No holdings yet.</div>';return}
  box.innerHTML=`<table class="data-table"><thead><tr><th>Ticker</th><th>Qty</th><th>Avg</th><th>Last</th><th>Value</th><th>P/L</th><th></th></tr></thead><tbody>${d.items.map(x=>`<tr><td>${escapeHtml(x.ticker)}</td><td>${x.quantity}</td><td>${money(x.avg_price)}</td><td>${money(x.last_price)}</td><td>${money(x.value)}</td><td class="${(x.pnl||0)>=0?'profit':'loss'}">${money(x.pnl)} (${x.pnl_pct??'—'}%)</td><td><button class="small-btn" onclick="removeHolding(${x.id})">Delete</button></td></tr>`).join("")}</tbody></table>`;
}
async function removeHolding(id){await fetch(`/api/portfolio/${id}`,{method:"DELETE"});loadPortfolio();toast("Holding deleted")}

async function loadAlerts(){
  const d=await (await fetch("/api/alerts")).json(); if(!d.success)return;
  const box=$("alertsList");
  if(!d.items.length){box.innerHTML='<div class="muted">No alerts created yet.</div>';return}
  box.innerHTML=d.items.map(x=>`<div class="alert-item ${x.triggered?'triggered':''}"><div><strong>${escapeHtml(x.ticker)}</strong><div class="muted">${x.direction} ₹${Number(x.target_price).toLocaleString("en-IN")} · Current ${x.current_price==null?'—':money(x.current_price)}</div></div><button class="small-btn" onclick="removeAlert(${x.id})">Delete</button></div>`).join("");
}
async function removeAlert(id){await fetch(`/api/alerts/${id}`,{method:"DELETE"});loadAlerts();toast("Alert deleted")}

document.addEventListener("DOMContentLoaded",()=>{
  $("searchBtn")?.addEventListener("click",()=>analyze($("tickerInput").value));
  $("tickerInput")?.addEventListener("keydown",e=>{if(e.key==="Enter")analyze(e.target.value)});
  $("watchBtn")?.addEventListener("click",addWatch);
  document.querySelectorAll(".quick-ticker").forEach(b=>b.addEventListener("click",()=>analyze(b.dataset.ticker)));
  $("holdingForm")?.addEventListener("submit",async e=>{e.preventDefault();const f=new FormData(e.target);const d=Object.fromEntries(f);const r=await fetch("/api/portfolio",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(d)});const j=await r.json();if(!j.success)return toast(j.error);e.target.reset();loadPortfolio();toast("Holding added")});
  $("alertForm")?.addEventListener("submit",async e=>{e.preventDefault();const f=new FormData(e.target);const d=Object.fromEntries(f);const r=await fetch("/api/alerts",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(d)});const j=await r.json();if(!j.success)return toast(j.error);e.target.reset();loadAlerts();toast("Alert created")});
  if($("tickerInput")){analyze($("tickerInput").value);loadWatchlist();loadPortfolio();loadAlerts();}
});
