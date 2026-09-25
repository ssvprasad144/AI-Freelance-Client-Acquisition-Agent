const API_BASE=import.meta.env.VITE_API_BASE_URL||"http://127.0.0.1:8000/api";
async function request(path,options={}){
  const response=await fetch(API_BASE+path,{headers:{"Content-Type":"application/json",...(options.headers||{})},...options});
  if(!response.ok){const text=await response.text();throw new Error(text||("Request failed: "+response.status));}
  return response.json();
}
export const api={
  dashboard:()=>request("/dashboard/"),
  leads:()=>request("/leads/"),
  analyze:(id)=>request("/leads/"+id+"/analyze/",{method:"POST"}),
  proposal:(id)=>request("/leads/"+id+"/proposal/",{method:"POST"}),
  activity:()=>request("/activity/"),
  createLead:(lead)=>request("/leads/",{method:"POST",body:JSON.stringify(lead)})
};