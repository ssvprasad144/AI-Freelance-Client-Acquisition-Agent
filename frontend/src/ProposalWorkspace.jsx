import React,{useEffect,useState} from "react";
import {api} from "./api";

export default function ProposalWorkspace({proposalId,onClose}){
 const [data,setData]=useState(null),[content,setContent]=useState(""),[instruction,setInstruction]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState("");
 async function load(){try{const x=await api.proposalWorkspace(proposalId);setData(x);setContent(x.current_content||"")}catch(e){setError(e.message)}}
 useEffect(()=>{if(new URLSearchParams(window.location.search).get("demo")==="1")return;void load()},[proposalId]);
 async function act(fn){setBusy(true);setError("");try{const x=await fn();setData(x);setContent(x.current_content||"")}catch(e){setError(e.message)}finally{setBusy(false)}}
 if(!data)return <section className="panel"><div className="empty">{error||"Loading proposal workspace…"}</div></section>;
 return <section className="panel proposal-workspace">
  <div className="panel-head"><div><div className="eyebrow">PROPOSAL WORKSPACE</div><h2>{data.lead_title}</h2></div><span className="draft">VERSION {data.current_version} · {data.status}</span></div>
  {error&&<div className="error">{error}</div>}
  <textarea value={content} onChange={e=>setContent(e.target.value)} rows={12}/>
  <div className="actions">
   <button disabled={busy||!content.trim()} onClick={()=>act(()=>api.editProposal(proposalId,content))}>Save new version</button>
   <input value={instruction} onChange={e=>setInstruction(e.target.value)} placeholder="e.g. make it shorter and more technical"/>
   <button className="secondary" disabled={busy||!instruction.trim()} onClick={()=>{const x=instruction;setInstruction("");return act(()=>api.reviseProposal(proposalId,x))}}>AI revise</button>
   <button className="secondary" onClick={onClose}>Close</button>
  </div>
  <div className="version-list">{(data.versions||[]).map(v=><div className="due-row" key={v.id}><span>v{v.version_number} · {v.source}</span><button className="secondary" disabled={busy} onClick={()=>act(()=>api.restoreProposal(proposalId,v.version_number))}>Restore</button></div>)}</div>
 </section>
}
