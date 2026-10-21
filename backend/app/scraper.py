"""Scheme data from myScheme (myscheme.gov.in), the Government of India's scheme portal.

The portal's own pages load their data from public JSON endpoints on the same
site. We call those same endpoints, and cache every response on disk so that:
  * we never hit the portal twice for the same thing (be polite), and
  * a live demo keeps working even if venue Wi-Fi drops (cache is warm).
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

BASE = "https://www.myscheme.gov.in"
SEARCH_URL = f"{BASE}/api/apisetu/search/schemes"
DETAIL_URL = f"{BASE}/api/apisetu/schemes"
HEADERS = {"user-agent": "Mozilla/5.0 (SchemeSaathi hackathon prototype)",
           "referer": f"{BASE}/search", "accept": "application/json"}

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache" / "myscheme"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SEARCH_TTL = 24 * 3600          # search results change rarely
DETAIL_TTL = 7 * 24 * 3600      # scheme details change even more rarely

# One HTTP client and request limit per event loop (tests may run several loops).
_per_loop: dict[int, tuple[httpx.AsyncClient, asyncio.Semaphore]] = {}


def _http() -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
    key = id(asyncio.get_running_loop())
    if key not in _per_loop:
        _per_loop[key] = (httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True),
                          asyncio.Semaphore(4))       # at most 4 requests to the portal at once
    return _per_loop[key]


# --------------------------------------------------------------------------- #
#  Disk cache
# --------------------------------------------------------------------------- #
def _cache_path(kind: str, key: str) -> Path:
    h = hashlib.sha256(key.encode()).hexdigest()[:20]
    return CACHE_DIR / f"{kind}-{h}.json"


def _cache_get(kind: str, key: str, ttl: int, allow_stale: bool = False) -> Any | None:
    p = _cache_path(kind, key)
    if not p.exists():
        return None
    if not allow_stale and time.time() - p.stat().st_mtime > ttl:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _cache_put(kind: str, key: str, value: Any) -> None:
    _cache_path(kind, key).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


async def _get_json(url: str, params: dict, kind: str, ttl: int) -> Any:
    key = url + "?" + json.dumps(params, sort_keys=True)
    hit = _cache_get(kind, key, ttl)
    if hit is not None:
        return hit
    try:
        client, sem = _http()
        async with sem:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, ValueError):
        stale = _cache_get(kind, key, ttl, allow_stale=True)
        if stale is not None:           # portal down: an old answer beats no answer
            return stale
        raise
    _cache_put(kind, key, data)
    return data


# --------------------------------------------------------------------------- #
#  Rich text -> plain text
# --------------------------------------------------------------------------- #
def rich_to_text(node: Any) -> str:
    """Flatten the portal's rich-text JSON tree into readable lines."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "\n".join(t for t in (rich_to_text(n) for n in node) if t.strip())
    if isinstance(node, dict):
        if "text" in node and "children" not in node:
            return node["text"]
        kids = node.get("children") or []
        inner = "".join(rich_to_text(k) if not isinstance(k, dict) or "children" not in k
                        else "\n" + rich_to_text(k) for k in kids)
        if node.get("type") == "list_item":
            inner = "- " + inner.strip()
        return inner
    return ""


def md_to_text(md: str | None) -> str:
    """Markdown from the portal -> plain text (drop ** and HTML entities, collapse blank lines)."""
    if not md:
        return ""
    t = html.unescape(md)
    t = re.sub(r"\*\*|__|`", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# --------------------------------------------------------------------------- #
#  Public API
# --------------------------------------------------------------------------- #
async def search(filters: list[dict], keyword: str = "", size: int = 20) -> dict:
    """Search schemes. `filters` is a list of {"identifier", "value"}.

    Portal semantics: several values for the SAME identifier are ORed,
    different identifiers are ANDed.
    """
    params = {"lang": "en", "q": json.dumps(filters), "keyword": keyword,
              "sort": "", "from": 0, "size": size}
    data = await _get_json(SEARCH_URL, params, "search", SEARCH_TTL)
    hits = data.get("data", {}).get("hits", {})
    items = []
    for h in hits.get("items", []):
        f = h.get("fields", {})
        items.append({
            "slug": f.get("slug"),
            "name": f.get("schemeName"),
            "short_title": f.get("schemeShortTitle"),
            "brief": f.get("briefDescription"),
            "level": f.get("level"),                    # Central / State
            "states": f.get("beneficiaryState") or [],
            "ministry": f.get("nodalMinistryName"),
            "department": f.get("nodalDepartmentName"),
            "categories": f.get("schemeCategory") or [],
            "tags": f.get("tags") or [],
            "close_date": f.get("schemeCloseDate"),
            "scheme_for": f.get("schemeFor"),           # Individual / Family / ...
        })
    return {"total": hits.get("page", {}).get("total", 0), "items": items}


async def detail(slug: str, lang: str = "en") -> dict:
    """Full scheme details (benefits, eligibility, how to apply, documents) as plain text."""
    data = await _get_json(DETAIL_URL, {"slug": slug, "lang": lang}, "detail", DETAIL_TTL)
    d = data.get("data") or {}
    has_native = bool(d.get(lang))
    if not (d.get(lang) or d.get("en")) and lang != "en":
        en_data = await _get_json(DETAIL_URL, {"slug": slug, "lang": "en"}, "detail", DETAIL_TTL)
        d = en_data.get("data") or {}

    lang_section = d.get(lang) or {}
    en_section = d.get("en") or {}
    basic = lang_section.get("basicDetails") or en_section.get("basicDetails") or {}
    basic_en = en_section.get("basicDetails") or {}
    content = lang_section.get("schemeContent") or en_section.get("schemeContent") or {}
    elig = (lang_section.get("eligibilityCriteria")
            or en_section.get("eligibilityCriteria")
            or d.get("eligibilityCriteria") or {})

    docs_text = ""
    if d.get("_id"):
        try:
            docs = await _get_json(f"{DETAIL_URL}/{d['_id']}/documents", {"lang": lang},
                                   "docs", DETAIL_TTL)
            dd = ((docs.get("data") or {}).get(lang)
                  or (docs.get("data") or {}).get("en") or {})
            docs_text = md_to_text(dd.get("documents_required_md")) or rich_to_text(
                dd.get("documents_required"))
        except (httpx.HTTPError, ValueError):
            pass

    apply = []
    app_process = lang_section.get("applicationProcess") or en_section.get("applicationProcess") or []
    for a in app_process:
        apply.append({"mode": a.get("mode"), "url": a.get("url"),
                      "steps": md_to_text(a.get("process_md")) or rich_to_text(a.get("process"))})

    label = lambda v: v.get("label") if isinstance(v, dict) else v   # noqa: E731
    scheme_name = basic.get("schemeName")
    official_name = basic_en.get("schemeName") or scheme_name

    # Fallback for schemes like ab-pmjay where detail endpoint data is empty
    if not scheme_name and slug == "ab-pmjay":
        from . import localization
        known_title = localization.get_known_scheme_title("ab-pmjay", lang)
        scheme_name = known_title or "Ayushman Bharat - Pradhan Mantri Jan Arogya Yojana"
        official_name = "Ayushman Bharat - Pradhan Mantri Jan Arogya Yojana"
        has_native = bool(known_title)
        brief_desc = "₹5,00,000 health insurance cover per family per year for secondary and tertiary care hospitalization."
        return {
            "slug": slug,
            "id": "ab-pmjay",
            "name": scheme_name,
            "official_name": official_name,
            "short_title": "AB-PMJAY",
            "level": "Central",
            "ministry": "Ministry Of Health & Family Welfare",
            "department": "Department of Health and Family Welfare",
            "scheme_for": "Family",
            "tags": ["Health", "Insurance", "Hospitalization"],
            "brief": brief_desc,
            "description": brief_desc,
            "benefit_type": "Composite",
            "benefits": "Cashless health cover up to ₹5,00,000 per family per year at all empaneled hospitals across India.",
            "eligibility": "Families identified under SECC 2011 database and low-income families as per state guidelines.",
            "exclusions": "Government employees and families covered under ESIC/CGHS.",
            "documents": "Aadhaar Card, Ration Card",
            "apply": [{"mode": "Online", "url": "https://mera.pmjay.gov.in", "steps": "Visit mera.pmjay.gov.in or any nearby Ayushman Arogya Mandir / CSC."}],
            "references": [],
            "url": f"{BASE}/schemes/{slug}",
            "source_language": lang if has_native else "en",
            "has_native": has_native,
        }

    return {
        "slug": slug,
        "id": d.get("_id"),
        "name": scheme_name,
        "official_name": official_name,
        "short_title": basic.get("schemeShortTitle") or basic_en.get("schemeShortTitle"),
        "level": label(basic.get("level")),
        "ministry": label(basic.get("nodalMinistryName")),
        "department": label(basic.get("nodalDepartmentName")),
        "scheme_for": basic.get("schemeFor"),
        "tags": basic.get("tags") or [],
        "brief": content.get("briefDescription"),
        "description": md_to_text(content.get("detailedDescription_md")),
        "benefit_type": label(content.get("benefitTypes")),
        "benefits": md_to_text(content.get("benefits_md")),
        "eligibility": md_to_text(elig.get("eligibilityDescription_md")),
        "exclusions": md_to_text(content.get("exclusions_md")),
        "documents": docs_text,
        "apply": apply,
        "references": content.get("references") or [],
        "url": f"{BASE}/schemes/{slug}",
        "source_language": lang if has_native else "en",
        "has_native": has_native,
    }
