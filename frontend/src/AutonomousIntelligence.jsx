import React,{useEffect,useState} from "react";
import {api} from "./api";

export default function AutonomousIntelligence({demoMode=false}){
 const [queue,setQueue]=useState([]),[outreach,setOutreach]=useState(null),[revenue,setRevenue]=useState(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 async function load(){setBusy(true);setError("");try{const [q,o,r]=await Promise.all([api.acquisitionQueue(),api.outreachStrategy(),api.revenue()]);setQueue(q);setOutreach(o);setRevenue(r)}catch(e){setError(e.message)}finally{setBusy(false)}}
 useEffect(()=>{if(import.meta.env.VITE_PUBLIC_PREVIEW!=="false")return;void load()},[]);
 async function execute(item){setBusy(true);try{await api.acquisitionAction(item.id,{action:item.recommended_action});await load()}catch(e){setError(e.message);setBusy(false)}}
 return <section className="panel" style={{marginTop:20}}>
  <div className="panel-head"><div><div className="eyebrow">PHASES 16–18 · CLOSED LOOP</div><h2>Autonomous Acquisition Intelligence</h2></div><button className="secondary" onClick={load} disabled={demoMode||busy}>{busy?"Updating…":"Refresh intelligence"}</button></div>
  {error&&<div className="error">{error}</div>}
  <div className="metrics">
   <article className="metric"><span>Priority actions</span><strong>{queue.length}</strong></article>
   <article className="metric"><span>Expected revenue</span><strong>{revenue?Number(revenue.expected_revenue||0).toFixed(2):"—"}</strong></article>
   <article className="metric"><span>Won revenue</span><strong>{revenue?Number(revenue.revenue||0).toFixed(2):"—"}</strong></article>
   <article className="metric"><span>Acquisition cost</span><strong>{revenue?Number(revenue.acquisition_cost||0).toFixed(2):"—"}</strong></article>
   <article className="metric"><span>ROI</span><strong>{revenue?Number(revenue.roi_percent||0).toFixed(1)+"%":"—"}</strong></article>
  </div>
  <div className="workspace" style={{marginTop:16}}>
   <div className="card"><div className="eyebrow">PHASE 16 · NEXT BEST ACTION</div><h3>Priority queue</h3>
    {!queue.length?<div className="empty">No active opportunities need action.</div>:queue.slice(0,12).map(x=><div className="due-row" key={x.id}><div><b>{x.lead_title}</b><div className="muted">Score {Number(x.score).toFixed(1)} · {x.recommended_action} · {x.reason||"model-driven priority"}</div></div><button className="secondary" disabled={demoMode||busy} onClick={()=>execute(x)}>Review action</button></div>)}
   </div>
   <div className="card"><div className="eyebrow">PHASE 17 · CHANNEL INTELLIGENCE</div><h3>Outreach strategy</h3>
    {!outreach?.plans?.length?<div className="empty">No eligible outreach plans.</div>:outreach.plans.slice(0,10).map(x=><div className="due-row" key={x.id}><div><b>{x.lead_title}</b><div className="muted">{x.channel} · Variant {x.variant} · {x.automatic?"automatic-capable":"manual"} · {x.status}</div></div></div>)}
   </div>
  </div>
  <div className="card" style={{marginTop:16}}><div className="eyebrow">PHASE 18 · REVENUE OPTIMIZATION</div><h3>Strategy attribution</h3>
   {!revenue?.by_strategy?.length?<div className="empty">Revenue attribution will appear as deal values are recorded.</div>:<div className="table-wrap"><table><thead><tr><th>Strategy</th><th>Leads</th><th>Revenue</th><th>Expected</th></tr></thead><tbody>{revenue.by_strategy.map((x,i)=><tr key={i}><td>{x.lead__discovery_strategy||"unspecified"}</td><td>{x.leads}</td><td>{Number(x.revenue||0).toFixed(2)}</td><td>{Number(x.expected||0).toFixed(2)}</td></tr>)}</tbody></table></div>}
  </div>
 </section>
}