import React,{useEffect,useState} from "react";
import {api} from "./api";

const labels={marketplace_bid:"Marketplace bid",linkedin_dm:"LinkedIn DM",reddit_reply:"Reddit reply",github_response:"GitHub response",email:"Email",job_application:"Job application",contact_form:"Contact form"};
const actionLabels={open_bid:"Open bid",open_profile:"Open profile",open_post:"Open post",open_issue:"Open issue",send_email:"Send email",open_application:"Open application",open_contact_form:"Open contact form"};

export default function OutreachCenter({demoMode=false}){
 const [items,setItems]=useState([]),[error,setError]=useState(""),[busy,setBusy]=useState(null);
 async function refresh(){try{setItems(await api.outreachReady())}catch(e){setError(e.message)}}
 useEffect(()=>{if(import.meta.env.VITE_PUBLIC_PREVIEW!=="false")return;void refresh()},[]);
 async function act(id,fn){setBusy(id);setError("");try{await fn();await refresh()}catch(e){setError(e.message)}finally{setBusy(null)}}
 function copy(text){navigator.clipboard?.writeText(text)}
 return <section className="panel outreach-center">
  <div className="panel-head"><div><div className="eyebrow">OUTREACH CENTER</div><h2>Ready-to-action proposals</h2></div><span className="draft">MANUAL ACTION · TRACKED</span></div>
  {error&&<div className="error">{error}</div>}
  {!items.length?<div className="empty">No proposal actions are waiting. Generate a proposal from a qualified lead.</div>:items.map(item=><article className="outreach-row" key={item.id}>
   <div className="outreach-main"><div className="lead-title">{item.lead_title}</div><div className="muted">{item.lead_source} · {labels[item.medium]||item.medium} · {item.status}</div><p>{item.message}</p></div>
   <div className="outreach-actions">
    {item.destination_url&&<button className="secondary" disabled={demoMode||busy===item.id} onClick={()=>act(item.id,async()=>{await api.openOutreach(item.id);window.open(item.destination_url,"_blank","noopener,noreferrer")})}>{actionLabels[item.action_type]||"Open destination"} ↗</button>}
    <button className="secondary" disabled={demoMode||busy===item.id} onClick={()=>copy(item.message)}>Copy proposal</button>
    {item.medium==="email"&&item.status==="approved"&&<button disabled={demoMode||busy===item.id} onClick={()=>act(item.id,()=>api.sendOutreach(item.id))}>Send email</button>}
    {item.medium!=="email"&&<button disabled={demoMode||busy===item.id} onClick={()=>act(item.id,()=>api.markOutreachSubmitted(item.id))}>Mark submitted</button>}
   </div>
  </article>)}
 </section>
}
