"""Step 5: a flashcard for one scheme, in the user's language, ready to be spoken.

The model only rewrites the portal's official text in simple words. Every
number it writes (amounts, ages, percentages) must appear in that text; if one
doesn't, the card is replaced by a plain English one built from the source.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Optional

from pydantic import BaseModel

from . import llm, localization, scraper
from .profile import LANGUAGE_NAMES, Profile

BRIEF_SYSTEM = """You turn an official Indian government scheme description into a
simple flashcard for someone with little schooling.
Write in the requested language and script. Short, everyday words. No jargon.
Use Western digits and the ₹ symbol for money.

HARD RULES
- Use ONLY facts from SOURCE. Never invent amounts, dates, ages or conditions.
- Every number you write must appear in SOURCE.
- If something is not in SOURCE, leave it out.
- Never tell them to share Aadhaar or bank details with anyone except the official office/portal.
FIELDS
- title: the scheme's name written in the requested language and script. CRITICAL: If the requested language is not English (e.g. Hindi), the title MUST be written in that language's script (e.g. Devanagari for Hindi: 'डॉ. बी.आर. अंबेडकर आवास नवीनीकरण योजना', 'राष्ट्रीय पारिवारिक लाभ योजना (NFBS)'). Keep well-known English acronyms in parentheses if helpful, but NEVER return a purely Latin/English title for non-English languages.
- one_line: what it gives, at most 12 words.
- benefit: the main benefit with the amount if SOURCE has one, at most 25 words.
- who_can_get: who is eligible, at most 30 words.
- how_to_apply: where and how to apply, at most 30 words.
- documents: up to 5 document names, each 1-4 words.
- spoken: a friendly spoken brief, at most 60 words, addressed to the person
  ("You can get ..."). If PERSON is given, mention why it may suit them, but do not
  promise they are eligible: say "you may be eligible"."""


class Brief(BaseModel):
    title: str
    one_line: str
    benefit: str
    who_can_get: str
    how_to_apply: str
    documents: list[str]
    spoken: str


class Card(BaseModel):
    slug: str
    language: str
    brief: Brief
    official_name: Optional[str] = None
    apply_modes: list[str] = []
    apply_url: Optional[str] = None
    source_url: str
    backend: str = "gemini"
    source_language: str = "en"
    translation_status: str = "verified"
    check: dict = {}


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[float]:
    out = set()
    for raw in _NUM.findall(text or ""):
        try:
            out.add(float(raw.replace(",", "")))
        except ValueError:
            pass
    return out


def _check(brief: Brief, source: str) -> dict:
    allowed = _numbers(source)
    # "Rs. 6000" in the source may be written "₹6,000"; lakh amounts may be expanded.
    allowed |= {n * 100000 for n in list(allowed)} | {n * 1000 for n in list(allowed)}
    allowed |= {1.0, 2.0, 3.0, 4.0, 5.0}   # "three instalments" in the source becomes "3"
    bad = []
    for name, text in brief.model_dump().items():
        texts = text if isinstance(text, list) else [text]
        for t in texts:
            bad += [{"field": name, "number": n} for n in _numbers(t) - allowed]
    return {"ok": not bad, "ungrounded": bad}


def _first(text: str, words: int) -> str:
    w = (text or "").replace("\n", " ").split()
    return " ".join(w[:words]) + ("…" if len(w) > words else "")


def _template(d: dict, language: str = "en") -> Brief:
    docs_val = d.get("documents") or ""
    if isinstance(docs_val, list):
        raw_docs = [str(x).strip() for x in docs_val]
    else:
        raw_docs = [l.lstrip("-•0123456789. ").strip() for l in docs_val.splitlines()]
    clean_docs = [x for x in raw_docs if x and len(x) < 60 and "document" not in x.lower()][:5]
    docs = [localization.translate_doc_name(x, language) for x in clean_docs]

    modes = [a["mode"] for a in d.get("apply") or [] if a.get("mode")]
    how_to = localization.translate_apply_modes(modes, language)

    eng_name = d.get("official_name") or d.get("name") or d.get("slug")
    loc_title = None
    if d.get("has_native"):
        loc_title = d.get("short_title") or d.get("name")
    else:
        known = localization.get_known_scheme_title(d.get("slug", ""), language)
        if known:
            loc_title = known

    if loc_title and loc_title != eng_name:
        if "(" in loc_title:
            title = loc_title
        else:
            title = f"{loc_title} ({eng_name})" if eng_name else loc_title
    else:
        title = d.get("short_title") or d.get("name") or d.get("slug", "")

    return Brief(title=title,
                 one_line=_first(d.get("brief") or "", 12),
                 benefit=_first(d.get("benefits") or "", 25),
                 who_can_get=_first(d.get("eligibility") or "", 30),
                 how_to_apply=how_to,
                 documents=docs,
                 spoken=_first(f"{title}. {d.get('brief') or ''}", 60))


def _source_text(d: dict) -> str:
    parts = {
        "NAME": d.get("name"), "SHORT NAME": d.get("short_title"), "LEVEL": d.get("level"),
        "MINISTRY": d.get("ministry"), "SUMMARY": d.get("brief"),
        "BENEFITS": d.get("benefits"), "ELIGIBILITY": d.get("eligibility"),
        "EXCLUSIONS": d.get("exclusions"), "DOCUMENTS": d.get("documents"),
        "HOW TO APPLY": "\n".join(f"[{a.get('mode')}] {a.get('steps', '')[:1200]}"
                                  for a in d.get("apply") or []),
    }
    return "\n\n".join(f"{k}:\n{v}" for k, v in parts.items() if v)[:9000]


_cache: dict[tuple, Card] = {}


async def card(slug: str, language: str = "en", profile: Profile | None = None) -> Card:
    key = (slug, language, profile.model_dump_json() if profile else "")
    if key in _cache:
        return _cache[key]
    d = await scraper.detail(slug, lang=language)
    if not d.get("name"):
        raise LookupError(f"Scheme '{slug}' not found")

    source = _source_text(d)
    person = None
    if profile:
        person = profile.model_dump(exclude_none=True,
                                    include={"age", "gender", "state", "occupation", "residence",
                                             "is_student", "family_members", "needs"})
    prompt = json.dumps({"LANGUAGE": f"{LANGUAGE_NAMES.get(language, 'English')} ({language})",
                         "PERSON": person, "SOURCE": source}, ensure_ascii=False, indent=1)

    backend, translation_status, check = "gemini", "ai", {}
    try:
        brief = await asyncio.to_thread(llm.generate, BRIEF_SYSTEM, prompt, Brief, 0.2)
        check = _check(brief, source)
        if not check["ok"]:             # a number we cannot back up: don't risk it
            brief = _template(d, language)
            backend = "portal" if d.get("has_native") else "template"
            translation_status = "verified" if d.get("has_native") else ("fallback_english" if language != "en" else "verified")
    except Exception as e:              # noqa: BLE001 - demo must not die
        brief = _template(d, language)
        backend = "portal" if d.get("has_native") else "template"
        translation_status = "verified" if d.get("has_native") else ("fallback_english" if language != "en" else "verified")
        check = {"error": str(e)[:200]}

    apply = d.get("apply") or []
    official_name = d.get("official_name") or d.get("name")
    c = Card(slug=slug, language=language, brief=brief, official_name=official_name,
             apply_modes=[a["mode"] for a in apply if a.get("mode")],
             apply_url=next((a["url"] for a in apply if a.get("url")), None),
             source_url=d.get("url", f"https://www.myscheme.gov.in/schemes/{slug}"),
             backend=backend,
             source_language=d.get("source_language", "en"),
             translation_status=translation_status, check=check)
    _cache[key] = c
    return c
