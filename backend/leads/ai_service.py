import json
from typing import Any
from django.conf import settings
from openai import OpenAI
from .knowledge import PROFILE
from .acquisition import personalize_proposal

SYSTEM_PROMPT="""You are a careful freelance lead qualification assistant.
Analyze a lead against the supplied developer profile.
Return only valid JSON with keys:
relevant (boolean), match_score (0-100), service_match (string),
requirements (array), pain_points (array), recommended_approach (string),
matching_projects (array), confidence (0-100).
Never invent facts. Use only information in the lead and profile.
"""

def deterministic_analysis(lead)->dict[str,Any]:
    text=" ".join([lead.title,lead.description,lead.budget_text," ".join(lead.technologies)]).lower()
    mapping={"ai":("AI Products",["AI Business Automation Dashboard","AI Interview"]),"automation":("Business Automation",["AI Business Automation Dashboard"]),"django":("Full-Stack Development",["CareerInnTech","AI Interview"]),"react":("Full-Stack Development",["3D Motion Portfolio","AI Business Automation Dashboard"]),"three.js":("Interactive Web",["3D Motion Portfolio"]),"three":("Interactive Web",["3D Motion Portfolio"]),"api":("Full-Stack Development",["CareerInnTech","AI Business Automation Dashboard"])}
    hits=[(svc,projects) for key,(svc,projects) in mapping.items() if key in text]
    projects=[]
    for _,ps in hits:
        for p in ps:
            if p not in projects: projects.append(p)
    return {"relevant":bool(hits),"match_score":min(95,30+len(hits)*15),"service_match":hits[0][0] if hits else "Needs review","requirements":lead.technologies,"pain_points":["Clarify scope, constraints, and delivery expectations."],"recommended_approach":"Confirm requirements, define the smallest deliverable, then propose an implementation plan grounded in existing project evidence.","matching_projects":projects[:4],"confidence":60 if hits else 30,"model":"deterministic-fallback","input_tokens":0,"output_tokens":0}

def analyze_lead(lead)->dict[str,Any]:
    if not settings.OPENAI_API_KEY:
        return deterministic_analysis(lead)
    client=OpenAI(api_key=settings.OPENAI_API_KEY)
    payload={"profile":PROFILE,"lead":{"title":lead.title,"company":lead.company,"description":lead.description,"budget_text":lead.budget_text,"technologies":lead.technologies,"lead_type":lead.lead_type}}
    response=client.responses.create(model=settings.OPENAI_MODEL,input=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":json.dumps(payload)}])
    data=json.loads(response.output_text)
    data["model"]=settings.OPENAI_MODEL
    usage=getattr(response,"usage",None)
    data["input_tokens"]=getattr(usage,"input_tokens",0) if usage else 0
    data["output_tokens"]=getattr(usage,"output_tokens",0) if usage else 0
    return data

def generate_proposal(lead,analysis)->str:
    if not settings.OPENAI_API_KEY:
        parts=personalize_proposal(lead,analysis)
        return "\n\n".join([parts["opening"],parts["fit"],parts["evidence"],parts["approach"],parts["next_step"],parts["closing"]])
        projects=", ".join(analysis.matching_projects or [])
        return f"Hi,\n\nI came across your request for {lead.title}. I work across {analysis.service_match or 'full-stack and AI development'} and can help structure the work around the requirements you listed. Relevant project evidence: {projects or 'available projects in my portfolio'}.\n\nI would first confirm the scope, current stack, integrations, and delivery target, then propose a focused implementation plan.\n\nRegards,\nSSVPrasad"
    client=OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt={"profile":PROFILE,"lead":{"title":lead.title,"company":lead.company,"description":lead.description,"budget_text":lead.budget_text,"technologies":lead.technologies},"analysis":{"service_match":analysis.service_match,"requirements":analysis.requirements,"pain_points":analysis.pain_points,"matching_projects":analysis.matching_projects,"recommended_approach":analysis.recommended_approach},"rules":["Reference only matching projects actually present in the profile.","Tie the opening sentence to the clients stated requirement.","Do not claim outcomes, clients, revenue, testimonials, or integrations not present in the profile.","Keep the proposal concise and specific.","End with a concrete low-friction next step."]}
    response=client.responses.create(model=settings.OPENAI_MODEL,input=[{"role":"system","content":"Draft a concise, professional freelance proposal. Never invent facts, clients, metrics, or integrations. Do not imply that any message has been sent."},{"role":"user","content":json.dumps(prompt)}])
    return response.output_text
