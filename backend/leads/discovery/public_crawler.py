import ipaddress
import json
import re
import socket
import time
from collections import defaultdict
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from django.conf import settings

class CrawlError(Exception):
    pass

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class _HTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title=[]
        self.text=[]
        self.links=[]
        self.meta={}
        self.jsonld=[]
        self._skip=0
        self._script_type=""
        self._script_buf=[]
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag in ("script","style","noscript"):
            self._skip+=1
            if tag=="script":
                self._script_type=(attrs.get("type") or "").lower()
                self._script_buf=[]
        if tag=="title": self._in_title=True
        if tag=="meta":
            key=(attrs.get("name") or attrs.get("property") or "").lower()
            content=attrs.get("content")
            if key and content: self.meta[key]=content.strip()
        if tag=="a" and attrs.get("href"): self.links.append(attrs["href"])
    def handle_endtag(self, tag):
        if tag in ("script","style","noscript"):
            if tag=="script" and "ld+json" in self._script_type:
                self.jsonld.append("".join(self._script_buf))
            self._skip=max(0,self._skip-1)
        if tag=="title": self._in_title=False
    def handle_data(self,data):
        if self._skip:
            if self._script_type and self._skip==1: self._script_buf.append(data)
            return
        if getattr(self,"_in_title",False): self.title.append(data.strip())
        elif data.strip(): self.text.append(re.sub(r"\s+"," ",data.strip()))

def _public_host(host):
    if not host: raise CrawlError("Missing hostname.")
    if host.lower() in {"localhost","localhost.localdomain"}: raise CrawlError("Private host blocked.")
    try:
        infos=socket.getaddrinfo(host,None,type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise CrawlError("Hostname could not be resolved.") from exc
    for info in infos:
        addr=ipaddress.ip_address(info[4][0])
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast or addr.is_unspecified:
            raise CrawlError("Private or non-public destination blocked.")
    return True

def _validate_url(url):
    p=urlparse(url)
    if p.scheme not in {"http","https"} or not p.hostname: raise CrawlError("Only public HTTP(S) URLs are allowed.")
    if p.username or p.password: raise CrawlError("URLs containing credentials are blocked.")
    _public_host(p.hostname)
    return p

def _robots_allowed(url):
    p=urlparse(url)
    robots_url=f"{p.scheme}://{p.netloc}/robots.txt"
    rp=RobotFileParser()
    rp.set_url(robots_url)
    try:
        req=Request(robots_url,headers={"User-Agent":settings.CRAWLER_USER_AGENT})
        with build_opener(_NoRedirect()).open(req,timeout=settings.CRAWLER_TIMEOUT_SECONDS) as response:
            if response.status>=400: return True
            body=response.read(settings.CRAWLER_MAX_ROBOTS_BYTES).decode("utf-8","replace")
        rp.parse(body.splitlines())
        return rp.can_fetch(settings.CRAWLER_USER_AGENT,url)
    except Exception:
        return bool(settings.CRAWLER_ALLOW_ROBOTS_FAILURE)

class PublicWebCrawler:
    def __init__(self):
        self.last_request=defaultdict(float)
        self.domain_counts=defaultdict(int)

    def _budget(self, host):
        now=time.monotonic()
        wait=settings.CRAWLER_MIN_DELAY_SECONDS-(now-self.last_request[host])
        if wait>0: time.sleep(min(wait,settings.CRAWLER_MAX_SLEEP_SECONDS))
        if self.domain_counts[host]>=settings.CRAWLER_MAX_PAGES_PER_DOMAIN:
            raise CrawlError("Per-domain crawl budget reached.")
        self.last_request[host]=time.monotonic()
        self.domain_counts[host]+=1

    def fetch(self,url,redirects=0):
        if not settings.CRAWLER_ENABLED: raise CrawlError("Public crawler is disabled.")
        p=_validate_url(url)
        if not _robots_allowed(url): raise CrawlError("robots.txt disallows crawling this URL.")
        self._budget(p.hostname.lower())
        req=Request(url,headers={"User-Agent":settings.CRAWLER_USER_AGENT,"Accept":"text/html,application/xhtml+xml,application/json;q=0.9"})
        opener=build_opener(_NoRedirect())
        try:
            response=opener.open(req,timeout=settings.CRAWLER_TIMEOUT_SECONDS)
        except Exception as exc:
            raise CrawlError(f"Fetch failed: {type(exc).__name__}") from exc
        with response:
            code=getattr(response,"status",200)
            if 300<=code<400:
                if redirects>=settings.CRAWLER_MAX_REDIRECTS: raise CrawlError("Redirect limit reached.")
                target=urljoin(url,response.headers.get("Location",""))
                _validate_url(target)
                return self.fetch(target,redirects+1)
            content_type=(response.headers.get("Content-Type") or "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type and "application/json" not in content_type:
                raise CrawlError("Unsupported content type.")
            data=response.read(settings.CRAWLER_MAX_RESPONSE_BYTES+1)
            if len(data)>settings.CRAWLER_MAX_RESPONSE_BYTES: raise CrawlError("Response exceeds crawler size limit.")
            return url,response.headers.get("Content-Type",""),data

    def extract(self,url):
        final_url,content_type,data=self.fetch(url)
        text=data.decode("utf-8","replace")
        if "json" in content_type:
            try: return {"url":final_url,"title":"","text":text[:settings.CRAWLER_MAX_TEXT_CHARS],"meta":{},"jsonld":[],"links":[]}
            except Exception: raise CrawlError("Invalid JSON response.")
        parser=_HTMLParser()
        parser.feed(text)
        clean=" ".join(parser.text)
        return {"url":final_url,"title":" ".join(parser.title).strip(),"text":clean[:settings.CRAWLER_MAX_TEXT_CHARS],"meta":parser.meta,"jsonld":parser.jsonld[:5],"links":parser.links[:settings.CRAWLER_MAX_LINKS]}

def enrich_leads(leads):
    crawler=PublicWebCrawler()
    enriched=[]
    for lead in leads[:settings.CRAWLER_MAX_LEADS_PER_CYCLE]:
        try:
            page=crawler.extract(lead["source_url"])
            if page["title"] and len(page["title"])>len(lead.get("title","")): lead["title"]=page["title"][:255]
            if page["text"]:
                lead["description"]=(lead.get("description","")+"\n\nPublic page context:\n"+page["text"])[:settings.CRAWLER_MAX_DESCRIPTION_CHARS]
            lead["source_url"]=page["url"]
            lead["crawler_metadata"]={"title":page["title"],"meta":page["meta"],"jsonld":page["jsonld"],"crawled_at":time.time()}
        except CrawlError as exc:
            lead["crawler_error"]=str(exc)
        enriched.append(lead)
    return enriched
