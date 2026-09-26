const API_BASE=import.meta.env.VITE_API_BASE_URL||"http://127.0.0.1:8000/api";
const tokenKey="freelance_agent_token";
export function getToken(){return localStorage.getItem(tokenKey)||""}
export function clearToken(){localStorage.removeItem(tokenKey)}
async function request(path,options={}){
  const headers={"Content-Type":"application/json",...(options.headers||{})};
  const token=getToken(); if(token) headers.Authorization="Token "+token;
  const response=await fetch(API_BASE+path,{...options,headers});
  if(response.status===401){clearToken();window.dispatchEvent(new Event("auth-expired"))}
  if(!response.ok){const text=await response.text();throw new Error(text||("Request failed: "+response.status))}
  return response.json();
}
function collection(data){return Array.isArray(data)?data:(data?.results||[])}
export const api={
 login:async(username,password)=>{const data=await request("/auth/login/",{method:"POST",body:JSON.stringify({username,password})});localStorage.setItem(tokenKey,data.token);return data},
 me:()=>request("/auth/me/"),
 logout:()=>clearToken(),
 dashboard:()=>request("/dashboard/"),
analytics:()=>request("/analytics/"),
discoveryProfiles:()=>request("/discovery/profiles/"),
 leads:(page=1)=>request("/leads/?page="+page+"&page_size=50"),
 analyze:id=>request("/leads/"+id+"/analyze/",{method:"POST"}),
 proposal:id=>request("/leads/"+id+"/proposal/",{method:"POST"}),
 approveProposal:id=>request("/leads/"+id+"/approve_proposal/",{method:"POST"}),
outreachReady:async()=>collection(await request("/outreach/ready/")),
openOutreach:id=>request("/outreach/"+id+"/open/",{method:"POST"}),
markOutreachSubmitted:id=>request("/outreach/"+id+"/mark-submitted/",{method:"POST"}),
sendOutreach:id=>request("/outreach/"+id+"/send/",{method:"POST"}),sendFollowup:id=>request("/followups/"+id+"/send/",{method:"POST"}),
 activity:async()=>collection(await request("/activity/")),
 discover:(query,source="live")=>request("/discovery/run/",{method:"POST",body:JSON.stringify({query,source})}),
 qualify:(limit=20)=>request("/discovery/qualify/",{method:"POST",body:JSON.stringify({limit})}),
 qualified:async()=>collection(await request("/leads/qualified/")),
 followups:async()=>collection(await request("/followups/")),
 dueFollowups:async()=>collection(await request("/followups/due/")),
 processDueFollowups:()=>request("/followups/process-due/",{method:"POST"}),
 createFollowup:data=>request("/followups/create/",{method:"POST",body:JSON.stringify(data)}),
 approveFollowup:id=>request("/followups/"+id+"/approve/",{method:"POST"}),
 createFollowUp:(id,data)=>request("/leads/"+id+"/followups/",{method:"POST",body:JSON.stringify(data)}),
 createLead:lead=>request("/leads/",{method:"POST",body:JSON.stringify(lead)}),
 setStatus:(id,status)=>request("/leads/"+id+"/set_status/",{method:"POST",body:JSON.stringify({status})}),
 createReply:(id,message,channel="email")=>request("/leads/"+id+"/replies/",{method:"POST",body:JSON.stringify({message,channel})})
};
