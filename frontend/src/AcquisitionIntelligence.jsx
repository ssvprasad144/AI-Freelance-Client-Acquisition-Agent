import React,{useEffect,useState} from "react";
import {api} from "./api";

export default function AcquisitionIntelligence(){
  const [analytics,setAnalytics]=useState(null),[clients,setClients]=useState([]),[meetings,setMeetings]=useState([]),[learning,setLearning]=useState([]),[loading,setLoading]=useState(false),[error,setError]=useState("");
  async function load(){
    setLoading(true);setError("");
    try{
      const [a,c,m,l]=await Promise.all([api.analytics(),api.clients(),api.meetings(),api.learning()]);
      setAnalytics(a);setClients(c);setMeetings(m);setLearning(l.stats||[]);
    }catch(e){setError(e.message)}finally{setLoading(false)}
  }
  useEffect(()=>{load()},[]);
  async function refreshLearning(){setLoading(true);try{const d=await api.refreshLearning();setLearning(d.stats||[]);const a=await api.analytics();setAnalytics(a)}catch(e){setError(e.message)}finally{setLoading(false)}}
  return <section className="panel" style={{marginTop:20}}>
    <div className="panel-head"><div><div className="eyebrow">PHASES 11–15</div><h2>Client Intelligence & Acquisition Learning</h2></div><button className="secondary" onClick={load} disabled={loading}>{loading?"Refreshing…":"Refresh"}</button></div>
    {error&&<div className="error">{error}</div>}
    {analytics&&<div className="metrics">
      {Object.entries(analytics.funnel||{}).slice(0,8).map(([k,v])=><article className="metric" key={k}><span>{k.replaceAll("_"," ")}</span><strong>{v}</strong></article>)}
    </div>}
    <div className="workspace" style={{marginTop:16}}>
      <div className="card">
        <div className="eyebrow">CLIENT MEMORY</div><h3>{clients.length} clients tracked</h3>
        {!clients.length?<div className="empty">No company history has been linked yet.</div>:clients.slice(0,12).map(c=><div className="due-row" key={c.id}><div><b>{c.company}</b><div className="muted">{c.domain||"No domain"} · {c.lead_count} opportunities · {c.status}</div></div>{c.intelligence&&<span className="status">INTELLIGENCE READY</span>}</div>)}
      </div>
      <div className="card">
        <div className="eyebrow">MEETINGS PIPELINE</div><h3>{meetings.length} meetings</h3>
        {!meetings.length?<div className="empty">No meetings recorded.</div>:meetings.slice(0,12).map(m=><div className="due-row" key={m.id}><div><b>{m.client_company||m.lead_title||"Meeting"}</b><div className="muted">{m.status} · {m.scheduled_at?new Date(m.scheduled_at).toLocaleString():"Time not set"}</div></div><span className="status">{m.next_action||"review"}</span></div>)}
      </div>
    </div>
    <div className="card" style={{marginTop:16}}>
      <div className="card-head"><div><div className="eyebrow">PHASE 15 · CLOSED LOOP</div><h3>Outcome learning</h3></div><button onClick={refreshLearning} disabled={loading}>Recalculate learning</button></div>
      {!learning.length?<div className="empty">Learning stats will appear after opportunities have outcomes.</div>:<div className="table-wrap"><table><thead><tr><th>Dimension</th><th>Key</th><th>Attempts</th><th>Qualified</th><th>Replies</th><th>Meetings</th><th>Wins</th><th>Reward</th></tr></thead><tbody>{learning.slice(0,25).map(x=><tr key={x.id}><td>{x.dimension}</td><td>{x.key}</td><td>{x.attempts}</td><td>{x.qualified}</td><td>{x.replies}</td><td>{x.meetings}</td><td>{x.wins}</td><td>{Number(x.reward||0).toFixed(1)}</td></tr>)}</tbody></table></div>}
    </div>
  </section>
}
