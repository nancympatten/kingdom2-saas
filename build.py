#!/usr/bin/env python3
"""
Build a static Software & SaaS Workflow Integrations Atlas.

Usage:
    python build.py
    python build.py --ping

Only Python's standard library is used. Place this file beside data.csv.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

# ---------------------------------------------------------------------------
# HARDCODED CONFIGURATION CONSTANTS — intentionally fixed as requested.
# ---------------------------------------------------------------------------
DOMAIN = "saas-connect-atlas.netlify.app"
BASE_URL = "https://saas-connect-atlas.netlify.app"
INDEXNOW_KEY = "b223b6b305c1482abbf0ed50c7ff86f7"
CSV_FILE = "data.csv"
OUTPUT_DIR = "dist"
STATE_FILE = "submitted_urls.json"
DRIP_BATCH_SIZE = 250

EXPECTED_HEADERS = [
    "slug", "title", "meta_description", "h1", "category", "summary",
    "data_table_html", "widget_html", "faq_q1", "faq_a1", "faq_q2", "faq_a2",
]
SITEMAP_LIMIT = 5000
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
TODAY = date.today().isoformat()
CURRENT_YEAR = datetime.now().year


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------
def esc(value: Any) -> str:
    """HTML-escape a value for safe text/attribute insertion."""
    return html.escape("" if value is None else str(value), quote=True)


def clean_slug(value: str) -> str:
    """Return a lowercase, URL-safe, single path segment."""
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if not value:
        raise ValueError("A CSV row has an empty or invalid slug.")
    if value in {".", ".."}:
        raise ValueError(f"Unsafe slug: {value!r}")
    return value


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def load_rows() -> list[dict[str, str]]:
    csv_path = Path(CSV_FILE)
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Could not find {CSV_FILE!r}. Put it in the same directory as build.py."
        )

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        missing = [name for name in EXPECTED_HEADERS if name not in headers]
        if missing:
            raise ValueError("CSV is missing required headers: " + ", ".join(missing))

        for line_number, raw in enumerate(reader, start=2):
            if not any(clean_text(v) for v in raw.values() if v is not None):
                continue
            row = {key: clean_text(raw.get(key, "")) for key in EXPECTED_HEADERS}
            slug = clean_slug(row["slug"])
            if slug in seen:
                raise ValueError(f"Duplicate slug {slug!r} on CSV line {line_number}.")
            seen.add(slug)
            row["slug"] = slug
            if not row["title"]:
                row["title"] = row["h1"] or slug.replace("-", " ").title()
            if not row["h1"]:
                row["h1"] = row["title"]
            if not row["summary"]:
                row["summary"] = row["meta_description"] or row["title"]
            if not row["category"]:
                row["category"] = "Workflow Integrations"
            rows.append(row)
    return rows


def json_script(value: Any) -> str:
    """Serialize JSON safely for embedding inside a script element."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )


def page_url(slug: str) -> str:
    return f"{BASE_URL}/{quote(slug, safe='-')}/"


def jsonld_for(row: dict[str, str], canonical: str) -> list[dict[str, Any]]:
    title = row["title"]
    summary = row["summary"]
    faqs = []
    for index in (1, 2):
        question = row[f"faq_q{index}"]
        answer = row[f"faq_a{index}"]
        if question and answer:
            faqs.append({
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            })

    graph: list[dict[str, Any]] = [
        {
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": title,
            "applicationCategory": "BusinessApplication",
            "operatingSystem": "Web",
            "description": summary,
            "url": canonical,
            "dateModified": TODAY,
        },
        {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": f"How to set up {title}",
            "description": summary,
            "dateModified": TODAY,
            "step": [
                {
                    "@type": "HowToStep",
                    "name": "Choose the connected applications",
                    "text": "Confirm the source and destination applications and the accounts you want to connect.",
                },
                {
                    "@type": "HowToStep",
                    "name": "Configure the workflow",
                    "text": "Select the trigger, map the required fields, and configure any filters or actions.",
                },
                {
                    "@type": "HowToStep",
                    "name": "Test and enable the integration",
                    "text": "Run a test with sample data, review the result, and enable the workflow when it behaves as expected.",
                },
            ],
        },
    ]
    if faqs:
        graph.append({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": faqs,
        })
    return graph


# ---------------------------------------------------------------------------
# Shared design system
# ---------------------------------------------------------------------------
CSS = r"""
:root{color-scheme:dark;--bg:#080d19;--panel:#101a2c;--panel2:#121f35;--line:#263653;
--text:#edf2ff;--muted:#a7b4ca;--accent:#8b7cff;--cyan:#52d6e8;--green:#55d6a4}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:
radial-gradient(ellipse at 15% 0%,rgba(91,76,210,.20),transparent 38%),
radial-gradient(ellipse at 90% 10%,rgba(35,174,198,.12),transparent 34%),var(--bg);
color:var(--text);font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:#a9c5ff;text-decoration:none}a:hover{color:#fff;text-decoration:underline}
.wrap{width:min(1120px,calc(100% - 32px));margin:auto}
header{padding:22px 0;border-bottom:1px solid rgba(160,180,220,.13)}
.nav{display:flex;align-items:center;justify-content:space-between;gap:18px}
.brand{font-weight:850;letter-spacing:-.04em;color:#fff;font-size:1.12rem}
.brand b{color:var(--cyan)}.nav small{color:var(--muted)}
main{padding:48px 0 70px}.eyebrow{color:var(--cyan);font-size:.76rem;font-weight:800;
letter-spacing:.14em;text-transform:uppercase}
h1{font-size:clamp(2rem,5vw,3.55rem);line-height:1.08;letter-spacing:-.055em;margin:12px 0 18px}
h2{font-size:1.45rem;letter-spacing:-.025em;margin:34px 0 12px}
h3{font-size:1.05rem;margin:0 0 8px}.muted,.subtle{color:var(--muted)}
.hero{max-width:850px;margin-bottom:26px}.fresh{display:inline-flex;gap:8px;align-items:center;
padding:6px 11px;border:1px solid rgba(85,214,164,.3);border-radius:99px;color:#a7f0d1;
background:rgba(85,214,164,.08);font-size:.78rem;font-weight:700}
.ai-tldr{padding:20px 22px;border:1px solid rgba(82,214,232,.32);border-left:4px solid var(--cyan);
border-radius:15px;background:linear-gradient(120deg,rgba(36,113,139,.19),rgba(24,35,62,.85));
box-shadow:0 15px 45px rgba(0,0,0,.16);margin:24px 0}
.ai-tldr strong{display:block;color:#9ceefa;font-size:.76rem;letter-spacing:.1em;text-transform:uppercase;margin-bottom:7px}
.ad-unit{min-height:12px;margin:24px 0;border:1px dashed rgba(150,170,210,.13);border-radius:10px}
.panel{background:linear-gradient(145deg,rgba(20,32,54,.96),rgba(12,20,36,.96));
border:1px solid var(--line);border-radius:18px;padding:22px;margin:20px 0;
box-shadow:0 18px 55px rgba(0,0,0,.16)}
table{width:100%;border-collapse:collapse;overflow:hidden;border-radius:12px}
th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:#cbd8f2;background:#17243b}td{color:#dce6f8}tr:last-child td{border-bottom:0}
.table-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px}
button,.button{display:inline-flex;align-items:center;justify-content:center;gap:8px;
border:0;border-radius:11px;padding:11px 17px;background:linear-gradient(115deg,#7567ff,#388cda);
color:white;font-weight:800;cursor:pointer;box-shadow:0 8px 25px rgba(88,99,235,.22)}
button:hover,.button:hover{filter:brightness(1.12);text-decoration:none}
input,select{width:100%;padding:13px 14px;border:1px solid #344664;border-radius:11px;
background:#0b1425;color:var(--text);font:inherit;outline:none}
input:focus,select:focus{border-color:var(--cyan);box-shadow:0 0 0 3px rgba(82,214,232,.12)}
.searchbar{display:grid;grid-template-columns:1fr auto;gap:10px}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:15px 0}
.pill{border:1px solid #344664;background:#111c30;color:#c5d1e6;padding:7px 12px;
border-radius:99px;font-size:.82rem;cursor:pointer}
.pill[aria-pressed=true]{background:#38336e;border-color:#8174ff;color:#fff}
.directory-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;margin-top:18px}
.result{display:block;padding:16px;border:1px solid var(--line);border-radius:14px;
background:rgba(17,29,49,.86);min-width:0}
.result strong{display:block;color:#f2f5ff;margin-bottom:5px}.result small{color:var(--muted)}
.related{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.related a{padding:12px 14px;border:1px solid var(--line);border-radius:11px;background:#111c30}
.workflow{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.workflow label{display:block;color:var(--muted);font-size:.86rem;margin-bottom:7px}
.output{padding:14px;border-radius:12px;background:#0a1425;border:1px solid var(--line);color:#c9f5ee}
.faq{padding:16px 0;border-bottom:1px solid var(--line)}.faq:last-child{border:0}
footer{border-top:1px solid rgba(160,180,220,.13);padding:24px 0 36px;color:var(--muted);font-size:.86rem}
@media(max-width:760px){main{padding-top:32px}.directory-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.workflow{grid-template-columns:1fr}.panel{padding:17px}}
@media(max-width:480px){.directory-grid,.related{grid-template-columns:1fr}.searchbar{grid-template-columns:1fr}
h1{font-size:2.15rem}.wrap{width:min(100% - 24px,1120px)}}
"""


def document_head(title: str, description: str, canonical: str, og_title: str | None = None) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#080d19">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(og_title or title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<style>{CSS}</style>
</head>"""


def footer() -> str:
    return f"""<footer><div class="wrap">
<p>Software &amp; SaaS Workflow Integrations Atlas · © {CURRENT_YEAR} ·
Reference year <span class="live-year">{CURRENT_YEAR}</span></p>
<p class="subtle">Calendar reference: <span class="live-updated">{date.today().strftime('%B %Y')}</span>.
Review integration permissions, pricing, and vendor documentation before enabling workflows.</p>
</div></footer>
<script>
(function(){{
  var now=new Date();
  document.querySelectorAll('.live-year').forEach(function(el){{el.textContent=now.getFullYear();}});
  document.querySelectorAll('.live-updated').forEach(function(el){{
    el.textContent=now.toLocaleDateString(undefined,{{month:'long',year:'numeric'}});
  }});
}})();
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# Integration detail pages
# ---------------------------------------------------------------------------
def related_links(row: dict[str, str], rows: list[dict[str, str]]) -> str:
    same = [r for r in rows if r["category"].casefold() == row["category"].casefold()
            and r["slug"] != row["slug"]][:6]
    if not same:
        same = [r for r in rows if r["slug"] != row["slug"]][:6]
    if not same:
        return "<p class=\"muted\">More integrations will appear here as the atlas grows.</p>"
    links = "".join(
        f'<a href="/{quote(r["slug"], safe="-")}/">{esc(r["title"])}</a>' for r in same
    )
    return f'<p class="muted">Explore Related {esc(row["category"])} Integrations</p><div class="related">{links}</div>'


def build_detail_page(row: dict[str, str], rows: list[dict[str, str]]) -> str:
    canonical = page_url(row["slug"])
    title = row["title"]
    meta = row["meta_description"] or row["summary"]
    display_title = f"{title} | Workflow Integration Guide {CURRENT_YEAR}"
    structured_data = json_script(jsonld_for(row, canonical))

    faq_html = []
    for index in (1, 2):
        q, a = row[f"faq_q{index}"], row[f"faq_a{index}"]
        if q and a:
            faq_html.append(
                f'<div class="faq"><h3>{esc(q)}</h3><p>{esc(a)}</p></div>'
            )
    faq_section = (
        '<section><h2>Frequently asked questions</h2><div class="panel">'
        + "".join(faq_html) + "</div></section>"
        if faq_html else ""
    )

    table_html = row["data_table_html"]
    if table_html:
        table_section = f'<section><h2>Integration details</h2><div class="panel"><div class="table-scroll">{table_html}</div></div></section>'
    else:
        table_section = ""

    widget_html = row["widget_html"]
    if widget_html:
        widget_section = f'<section><h2>Interactive workflow configurator</h2><div class="panel">{widget_html}</div></section>'
    else:
        widget_section = """
<section><h2>Workflow setup planner</h2>
<div class="panel">
<div class="workflow">
<div><label for="trigger">Trigger event</label><input id="trigger" placeholder="e.g. New form submission"></div>
<div><label for="action">Resulting action</label><input id="action" placeholder="e.g. Create a CRM contact"></div>
</div>
<p><button type="button" id="make-plan">Generate workflow outline</button></p>
<div class="output" id="workflow-output" aria-live="polite">Choose a trigger and action to create a simple workflow outline.</div>
</div>
<script>
(function(){
 var btn=document.getElementById('make-plan');
 if(!btn)return;
 btn.addEventListener('click',function(){
  var trigger=document.getElementById('trigger').value.trim();
  var action=document.getElementById('action').value.trim();
  document.getElementById('workflow-output').textContent=
   trigger&&action ? 'When '+trigger+', then '+action+'. Test with sample data before enabling.' :
   'Enter both a trigger and an action to build the outline.';
 });
})();
</script>
</section>"""

    return (
        document_head(display_title, meta, canonical)
        + f'<body><header><div class="wrap nav"><a class="brand" href="/">SAAS<b>ATLAS</b></a>'
          f'<small>Software workflow knowledge base</small></div></header>'
        + '<main class="wrap"><div class="hero">'
        + f'<div class="eyebrow">{esc(row["category"])}</div><h1>{esc(row["h1"])}</h1>'
        + f'<span class="fresh">Reviewed for reference year {CURRENT_YEAR}</span></div>'
        + f'<div class="ai-tldr"><strong>AI Quick Answer</strong><p>{esc(row["summary"])}</p></div>'
        + '<div class="ad-unit" aria-label="Advertisement"></div>'
        + table_section
        + widget_section
        + '<div class="ad-unit" aria-label="Advertisement"></div>'
        + '<section><h2>How this workflow fits together</h2><div class="panel">'
        + '<ol><li>Identify the source event in the first application.</li>'
          '<li>Choose the destination action and map the fields that need to move.</li>'
          '<li>Apply filters, test with sample records, and monitor the first live runs.</li></ol>'
        + '<p class="muted">Check each provider’s current API limits, plan requirements, and permission scopes before deployment.</p>'
        + '</div></section>'
        + faq_section
        + '<section><h2>Related integrations</h2>' + related_links(row, rows) + '</section>'
        + '</main>'
        + '<script type="application/ld+json">' + structured_data + '</script>'
        + footer()
    )


# ---------------------------------------------------------------------------
# Homepage and search index
# ---------------------------------------------------------------------------
def build_search_index(rows: list[dict[str, str]], output: Path) -> None:
    records = [{
        "slug": r["slug"], "title": r["title"], "category": r["category"],
        "summary": r["summary"],
    } for r in rows]
    (output / "search-index.json").write_text(
        json.dumps(records, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def build_homepage(rows: list[dict[str, str]], output: Path) -> None:
    categories = sorted({r["category"] for r in rows}, key=str.casefold)
    canonical = BASE_URL + "/"
    description = "Explore software and SaaS workflow integrations, app connections, setup guides, and practical automation patterns."
    title = f"Software & SaaS Workflow Integrations Atlas | {CURRENT_YEAR}"
    category_buttons = "".join(
        f'<button class="pill" type="button" data-category="{esc(cat)}" aria-pressed="false">{esc(cat)}</button>'
        for cat in categories
    )
    initial_cards = "".join(
        f'<a class="result" href="/{quote(r["slug"], safe="-")}/" data-card>'
        f'<strong>{esc(r["title"])}</strong><small>{esc(r["category"])}</small>'
        f'<p class="muted">{esc(r["summary"][:150])}</p></a>'
        for r in rows[:60]
    )
    page = (
        document_head(title, description, canonical)
        + '<body><header><div class="wrap nav"><a class="brand" href="/">SAAS<b>ATLAS</b></a>'
          '<small>10,000-page integration directory</small></div></header>'
        + '<main class="wrap"><section class="hero"><div class="eyebrow">The workflow connection directory</div>'
        + f'<h1>Find the right SaaS integration for your workflow</h1>'
        + '<p class="muted">Search app connections, explore integration categories, and plan practical automations across your software stack.</p>'
        + f'<span class="fresh">Atlas reference year {CURRENT_YEAR}</span></section>'
        + '<section class="panel"><h2>Search integrations</h2>'
        + '<div class="searchbar"><input id="search" type="search" autocomplete="off" placeholder="Search apps, workflows, or outcomes…" aria-label="Search integrations">'
        + '<button id="clear" type="button">Clear</button></div>'
        + '<div class="filters" id="filters"><button class="pill" data-category="all" aria-pressed="true" type="button">All categories</button>'
        + category_buttons + '</div>'
        + f'<p class="muted" id="count" aria-live="polite">Loading {len(rows):,} integrations…</p>'
        + f'<div class="directory-grid" id="results">{initial_cards}</div></section>'
        + '<div class="ad-unit" aria-label="Advertisement"></div>'
        + '<section><h2>How to use the atlas</h2><div class="panel"><ol>'
        + '<li>Search by application name, workflow, or the outcome you want.</li>'
        + '<li>Open a result to review its summary, setup considerations, and related integrations.</li>'
        + '<li>Verify current vendor documentation and permissions before connecting production accounts.</li>'
        + '</ol></div></section></main>'
        + footer()
        + '<script>'
        + r"""
(function(){
 const search=document.getElementById('search');
 const results=document.getElementById('results');
 const count=document.getElementById('count');
 const filters=document.getElementById('filters');
 const clear=document.getElementById('clear');
 let data=[];
 let active='all';
 function safe(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
 function render(){
  const q=search.value.trim().toLocaleLowerCase();
  const matches=data.filter(item=>{
   const categoryOK=active==='all'||item.category===active;
   const hay=(item.title+' '+item.category+' '+item.summary+' '+item.slug).toLocaleLowerCase();
   return categoryOK&&(!q||hay.includes(q));
  });
  count.textContent=matches.length.toLocaleString()+' matching integrations';
  results.innerHTML=matches.slice(0,120).map(item=>
   '<a class="result" href="/'+encodeURIComponent(item.slug)+'/"><strong>'+safe(item.title)+'</strong>'+
   '<small>'+safe(item.category)+'</small><p class="muted">'+safe((item.summary||'').slice(0,150))+'</p></a>'
  ).join('')||'<p class="muted">No integrations match that search. Try another term or category.</p>';
  if(matches.length>120)count.textContent+=' · Showing first 120; refine your search for more precise results.';
 }
 filters.addEventListener('click',e=>{
  const button=e.target.closest('button[data-category]');if(!button)return;
  active=button.dataset.category;
  filters.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
  render();
 });
 search.addEventListener('input',render);
 clear.addEventListener('click',()=>{search.value='';active='all';
  filters.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.category==='all')));
  render();search.focus();});
 fetch('/search-index.json').then(r=>{if(!r.ok)throw new Error('index unavailable');return r.json();})
  .then(items=>{data=items;render();})
  .catch(()=>{data=__INITIAL_DATA__;render();});
})();
"""
        + "\n</script><script>const __INITIAL_DATA__="
        + json_script([{
            "slug": r["slug"], "title": r["title"], "category": r["category"],
            "summary": r["summary"],
        } for r in rows])
        + ";</script></body></html>"
    )
    (output / "index.html").write_text(page, encoding="utf-8")


# ---------------------------------------------------------------------------
# Sitemaps, robots, and IndexNow key verification file
# ---------------------------------------------------------------------------
def xml_escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))


def write_sitemaps(rows: list[dict[str, str]], output: Path) -> list[str]:
    urls = [BASE_URL + "/"] + [page_url(r["slug"]) for r in rows]
    chunks = [urls[i:i + SITEMAP_LIMIT] for i in range(0, len(urls), SITEMAP_LIMIT)]
    # Always produce the two specifically requested sitemap files.
    while len(chunks) < 2:
        chunks.append([])
    sitemap_names = []
    for number, chunk in enumerate(chunks, start=1):
        name = f"sitemap-{number}.xml"
        sitemap_names.append(name)
        entries = "".join(
            "<url><loc>" + xml_escape(url) + "</loc><lastmod>" + TODAY
            + "</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>"
            for url in chunk
        )
        content = '<?xml version="1.0" encoding="UTF-8"?>\n' \
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' \
                  + entries + "</urlset>"
        (output / name).write_text(content, encoding="utf-8")

    index_entries = "".join(
        f"<sitemap><loc>{BASE_URL}/{name}</loc><lastmod>{TODAY}</lastmod></sitemap>"
        for name in sitemap_names
    )
    index_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' \
                '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' \
                + index_entries + "</sitemapindex>"
    (output / "sitemap.xml").write_text(index_xml, encoding="utf-8")
    return urls


def write_robots_and_key(output: Path) -> None:
    (output / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: " + BASE_URL + "/sitemap.xml\n",
        encoding="utf-8",
    )
    (output / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")


# ---------------------------------------------------------------------------
# IndexNow drip submission
# ---------------------------------------------------------------------------
def read_submitted_urls() -> set[str]:
    path = Path(STATE_FILE)
    if not path.exists():
        return set()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"Could not read valid JSON from {STATE_FILE}: {exc}") from exc
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError(f"{STATE_FILE} must contain a JSON array of URL strings.")
    return set(value)


def ping_indexnow(all_urls: list[str]) -> int:
    submitted = read_submitted_urls()
    pending = [url for url in all_urls if url not in submitted][:DRIP_BATCH_SIZE]
    if not pending:
        print("IndexNow: no unsubmitted URLs remain.")
        return 0

    payload = {
        "host": DOMAIN,
        "key": INDEXNOW_KEY,
        "keyLocation": f"{BASE_URL}/{INDEXNOW_KEY}.txt",
        "urlList": pending,
    }
    request = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "SaaS-Connect-Atlas-IndexNow/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.getcode()
            body = response.read(2048).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read(2048).decode("utf-8", errors="replace")
        print(f"IndexNow failed: HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"IndexNow request failed: {exc}", file=sys.stderr)
        return 1

    if status in (200, 202):
        submitted.update(pending)
        Path(STATE_FILE).write_text(
            json.dumps(sorted(submitted), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"IndexNow accepted {len(pending)} URLs (HTTP {status}).")
        return 0

    print(f"IndexNow returned unexpected HTTP {status}: {body}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Build orchestration
# ---------------------------------------------------------------------------
def build() -> list[str]:
    rows = load_rows()
    output = Path(OUTPUT_DIR)
    output.mkdir(parents=True, exist_ok=True)

    # Remove only generated HTML page directories from the prior build. Keep
    # state files and other user-managed files outside the generated tree.
    for row in rows:
        page_dir = output / row["slug"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(
            build_detail_page(row, rows), encoding="utf-8"
        )

    build_search_index(rows, output)
    build_homepage(rows, output)
    urls = write_sitemaps(rows, output)
    write_robots_and_key(output)

    print(f"Built {len(rows):,} integration pages in {output.resolve()}")
    print(f"Generated {len(urls):,} canonical URLs across sitemap files.")
    return urls


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the SaaS Connect Atlas static site and optionally submit an IndexNow batch."
    )
    parser.add_argument(
        "--ping", action="store_true",
        help="Build the site, then submit the next 250 unsubmitted URLs to IndexNow.",
    )
    args = parser.parse_args()
    try:
        urls = build()
        if args.ping:
            return ping_indexnow(urls)
        return 0
    except (FileNotFoundError, ValueError, OSError, csv.Error) as exc:
        print(f"Build error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
