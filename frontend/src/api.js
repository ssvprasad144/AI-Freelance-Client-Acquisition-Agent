const configuredBase=import.meta.env.VITE_API_BASE_URL?.trim();
if(import.meta.env.PROD&&!configuredBase){throw new Error("VITE_API_BASE_URL must be configured for the production frontend.");}
const API_BASE=(configuredBase||"http://127.0.0.1:8000/api").replace(/\/$/,"");
const tokenKey="freelance_agent_token";
export function getToken(){return localStorage.getItem(tokenKey)||""}
export function clearToken(){localStorage.removeItem(tokenKey)}
async function request(path,options={}){
  const headers={"Content-Type":"application/json",...(options.headers||{})};
  const token=getToken(); if(token) headers.Authorization="Token "+token;
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),Number(options.timeoutMs||30000));
  const {timeoutMs,...fetchOptions}=options;
  try{
    const response=await fetch(API_BASE+path,{...fetchOptions,headers,signal:fetchOptions.signal||controller.signal});
    if(response.status===401){clearToken();window.dispatchEvent(new Event("auth-expired"))}
    const contentType=response.headers.get("content-type")||"";
    const payload=contentType.includes("application/json")?await response.json():await response.text();
    if(!response.ok){
      const detail=typeof payload==="string"?payload:(payload?.detail||payload?.error||"");
      throw new Error(detail||("Request failed ("+response.status+")"));
    }
    return payload;
  }catch(error){
    if(error.name==="AbortError")throw new Error("Live search exceeded its time limit. The backend may still be processing; check discovery status and logs.");
    if(error instanceof TypeError)throw new Error("Unable to reach the API. Check the backend URL and your connection.");
    throw error;
  }finally{clearTimeout(timeout)}
}
function collection(data){return Array.isArray(data)?data:(data?.results||[])}
export const api={
 login:async(username,password)=>{const data=await request("/auth/login/",{method:"POST",body:JSON.stringify({username,password})});localStorage.setItem(tokenKey,data.token);return data},
 me:()=>request("/auth/me/"),logout:()=>clearToken(),health:()=>request("/health/"),
 dashboard:()=>request("/dashboard/"),analytics:()=>request("/analytics/"),
 clients:async()=>collection(await request("/clients/")),client:id=>request("/clients/"+id+"/"),clientIntelligence:id=>request("/clients/"+id+"/intelligence/",{method:"POST"}),
 meetings:async()=>collection(await request("/meetings/")),createMeeting:data=>request("/meetings/create/",{method:"POST",body:JSON.stringify(data)}),updateMeeting:(id,data)=>request("/meetings/"+id+"/",{method:"PATCH",body:JSON.stringify(data)}),
 learning:()=>request("/learning/"),refreshLearning:()=>request("/learning/refresh/",{method:"POST"}),
 acquisitionQueue:()=>request("/acquisition/queue/"),acquisitionNextActions:()=>request("/acquisition/next-actions/"),recalculateAcquisition:()=>request("/acquisition/recalculate/",{method:"POST"}),acquisitionAction:(id,data)=>request("/acquisition/"+id+"/action/",{method:"POST",body:JSON.stringify(data)}),
 outreachStrategy:()=>request("/outreach/strategy/"),createOutreachPlan:data=>request("/outreach/plans/",{method:"POST",body:JSON.stringify(data)}),approveOutreachPlan:id=>request("/outreach/plans/"+id+"/approve/",{method:"POST"}),
 revenue:()=>request("/revenue/"),revenueRecords:async()=>collection(await request("/revenue/records/")),recordRevenue:data=>request("/revenue/record/",{method:"POST",body:JSON.stringify(data)}),syncClients:()=>request("/clients/sync/",{method:"POST"}),
 discoveryProfiles:()=>request("/discovery/profiles/"),leads:(page=1)=>request("/leads/?page="+page+"&page_size=50"),analyze:id=>request("/leads/"+id+"/analyze/",{method:"POST"}),proposal:id=>request("/leads/"+id+"/proposal/",{method:"POST"}),
 proposals:()=>request("/proposals/"),proposalWorkspace:id=>request("/proposals/"+id+"/"),editProposal:(id,content)=>request("/proposals/"+id+"/edit/",{method:"PUT",body:JSON.stringify({content})}),reviseProposal:(id,instruction)=>request("/proposals/"+id+"/revise/",{method:"POST",body:JSON.stringify({instruction})}),restoreProposal:(id,version_number)=>request("/proposals/"+id+"/restore/",{method:"POST",body:JSON.stringify({version_number})}),approveProposal:id=>request("/leads/"+id+"/approve_proposal/",{method:"POST"}),
 outreachReady:async()=>collection(await request("/outreach/ready/")),openOutreach:id=>request("/outreach/"+id+"/open/",{method:"POST"}),markOutreachSubmitted:id=>request("/outreach/"+id+"/mark-submitted/",{method:"POST"}),sendOutreach:id=>request("/outreach/"+id+"/send/",{method:"POST"}),sendFollowup:id=>request("/followups/"+id+"/send/",{method:"POST"}),
 activity:async()=>collection(await request("/activity/")),discover:(query,source="live")=>request("/discovery/run/",{method:"POST",body:JSON.stringify({query,source}),timeoutMs:240000}),qualify:(limit=20)=>request("/discovery/qualify/",{method:"POST",body:JSON.stringify({limit}),timeoutMs:90000}),qualified:async()=>collection(await request("/leads/qualified/")),
 followups:async()=>collection(await request("/followups/")),dueFollowups:async()=>collection(await request("/followups/due/")),processDueFollowups:()=>request("/followups/process-due/",{method:"POST"}),createFollowup:data=>request("/followups/create/",{method:"POST",body:JSON.stringify(data)}),approveFollowup:id=>request("/followups/"+id+"/approve/",{method:"POST"}),createFollowUp:(id,data)=>request("/leads/"+id+"/followups/",{method:"POST",body:JSON.stringify(data)}),createFollowupSequence:(id,data={})=>request("/leads/"+id+"/followup-sequence/",{method:"POST",body:JSON.stringify(data)}),followupSequences:async()=>collection(await request("/followup-sequences/")),cancelFollowupSequence:id=>request("/followup-sequences/"+id+"/cancel/",{method:"POST"}),
 createLead:lead=>request("/leads/",{method:"POST",body:JSON.stringify(lead)}),setStatus:(id,status)=>request("/leads/"+id+"/set_status/",{method:"POST",body:JSON.stringify({status})}),createReply:(id,message,channel="email")=>request("/leads/"+id+"/replies/",{method:"POST",body:JSON.stringify({message,channel})})
};
