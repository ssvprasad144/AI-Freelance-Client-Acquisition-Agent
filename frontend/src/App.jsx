import React,{useEffect,useMemo,useState} from "react";
import {api} from "./api";

const DEMO_LEADS=[
 {title:"AI lead qualification workflow",company:"Sample SaaS",description:"Build an automated workflow that qualifies inbound leads, classifies intent, and prepares a sales-ready summary.",source:"mock",lead_type:"freelance",budget_text:"$800-$1,500",technologies:["AI","Python","API"],contact_info:{}},
 {title:"Django operations dashboard",company:"Sample Operations Team",description:"Need a Django backend with REST APIs and automated internal workflow steps for an operations dashboard.",source:"mock",lead_type:"direct",budget_text:"$600-$1,000",technologies:["Django","REST API","PostgreSQL"],contact_info:{}},
 {title:"Interactive product landing page",company:"Sample Startup",description:"Create a polished React landing page with a lightweight 3D section and clear product storytelling.",source:"mock",lead_type:"startup",budget_text:"$700-$1,200",technologies:["React","Three.js","Vite"],contact_info:{}}
];

function App(){
 const [dashboard,setDashboard]=useState({});
 const [leads,setLeads]=useState([]);
 const [selected,setSelected]=useState(null);
 const [analysis,setAnalysis]=useState(null);
 const [proposal,setProposal]=useState(null);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState("");
 const [filter,setFilter]=useState("all");

 async function refresh(){
   const [d,l]=await Promise.all([api.dashboard(),api.leads()]);
   setDashboard(d);setLeads(l);
   if(selected)setSelected(l.find(x=>x.id===selected.id)||null);
 }
 useEffect(()=>{refresh().catch(e=>setError(e.message));},[]);

 async function seed(){
   setLoading(true);setError("");
   try{for(const lead of DEMO_LEADS)await api.createLead(lead);await refresh();}
   catch(e){setError(e.message);}finally{setLoading(false);}
 }
 const visible=useMemo(()=>filter==="all"?leads:leads.filter(l=>l.status===filter),[leads,filter]);

 async function selectLead(lead){
   setSelected(lead);setAnalysis(lead.analysis||null);setProposal(null);
 }
 async function runAnalysis(){
   if(!selected)return;
   setLoading(true);setError("");
   try{const data=await api.analyze(selected.id);setSelected(data);setAnalysis(data.analysis);await refresh();}
   catch(e){setError(e.message);}finally{setLoading(false);}
 }
 async function generateProposal(){
   if(!selected||!analysis)return;
   setLoading(true);setError("");
   try{setProposal(await api.proposal(selected.id));await refresh();}
   catch(e){setError(e.message);}finally{setLoading(false);}
 }

 return <div className="app">
  <header className="topbar">
   <div><div className="eyebrow">SSVPRASAD · V1</div><h1>AI Freelance Acquisition Agent</h1><p>Turn opportunities into qualified, reviewable outreach drafts.</p></div>
   <div className="header-actions"><span className="safe">SANDBOX · OUTBOUND DISABLED</span><button onClick={seed} disabled={loading}>Load demo leads</button></div>
  </header>
  {error&&<div className="error">{error}</div>}
  <section className="metrics">
   {[["Opportunities",dashboard.opportunities||0],["Qualified",dashboard.qualified||0],["High Match",dashboard.high_match||0],["Proposals",dashboard.proposals||0]].map(([k,v])=><article className="metric" key={k}><span>{k}</span><strong>{v}</strong></article>)}
  </section>
  <main className="workspace">
   <aside className="panel pipeline">
    <div className="panel-head"><div><div className="eyebrow">PIPELINE</div><h2>Opportunities</h2></div>
      <select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All</option><option value="new">New</option><option value="qualified">Qualified</option><option value="proposal">Proposal</option></select>
    </div>
    {!visible.length?<div className="empty">No leads yet. Load demo leads to test the workflow.</div>:
      <div>{visible.map(lead=><button key={lead.id} className={"lead-row "+(selected?.id===lead.id?"active":"")} onClick={()=>selectLead(lead)}>
       <div className="lead-title">{lead.title}</div><div className="muted">{lead.company||"Independent"} · {lead.source}</div>
       <div className="chips"><span>{lead.status}</span>{(lead.technologies||[]).slice(0,3).map(t=><span key={t}>{t}</span>)}</div>
      </button>)}</div>}
   </aside>
   <section className="panel detail">
    {!selected?<div className="empty large"><div><div className="empty-icon">✦</div><h3>Select an opportunity</h3><p>Inspect fit, analyze requirements, then generate a proposal draft for review.</p></div></div>:
    <div>
      <div className="detail-head"><div><div className="eyebrow">{selected.lead_type}</div><h2>{selected.title}</h2><p>{selected.company||"Independent"}</p></div><span className="status">{selected.status}</span></div>
      <div className="detail-body">
       <p className="description">{selected.description}</p>
       <div className="facts"><div><span>Source</span><b>{selected.source}</b></div><div><span>Budget</span><b>{selected.budget_text||"Not stated"}</b></div><div><span>Tech</span><b>{(selected.technologies||[]).join(", ")||"Not stated"}</b></div></div>
       <div className="actions"><button onClick={runAnalysis} disabled={loading}>{loading?"Working…":"Analyze opportunity"}</button><button className="secondary" onClick={generateProposal} disabled={loading||!analysis}>Generate proposal</button></div>
       {analysis&&<div className="card">
        <div className="card-head"><div><div className="eyebrow">AI QUALIFICATION</div><h3>{analysis.service_match||"Needs review"}</h3></div><div className="score">{analysis.match_score}</div></div>
        <div className="scorebar"><span style={{width:(analysis.match_score||0)+"%"}}/></div>
        <div className="grid"><div><span>Relevant</span><b>{analysis.relevant?"Yes":"Needs review"}</b></div><div><span>Confidence</span><b>{analysis.confidence}/100</b></div></div>
        <div className="block"><span>Requirements</span><p>{(analysis.requirements||[]).join(", ")||"None extracted"}</p></div>
        <div className="block"><span>Pain points</span><p>{(analysis.pain_points||[]).join(" ")}</p></div>
        <div className="block"><span>Recommended approach</span><p>{analysis.recommended_approach}</p></div>
        <div className="block"><span>Matching projects</span><p>{(analysis.matching_projects||[]).join(" · ")||"None"}</p></div>
       </div>}
       {proposal&&<div className="card proposal"><div className="card-head"><div><div className="eyebrow">OUTREACH DRAFT</div><h3>Review before sending</h3></div><span className="draft">DRAFT · NOT SENT</span></div><pre>{proposal.message}</pre></div>}
      </div>
    </div>}
   </section>
  </main>
 </div>
}
export default App;