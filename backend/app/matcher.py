"""Step 4: confirmed profile -> matching schemes.

No AI here. The profile is turned into searches on the myScheme portal using
its own official eligibility filters (state, gender, age, caste, occupation,
student, disability, BPL ...). Each search that finds a scheme adds a plain
reason ("For your work: Farmer", "For your daughter's studies"), and schemes
found by more searches rank higher.

Two safety nets on top of the portal's filters:
  * keyword searches are fuzzy, so a keyword hit only counts if the scheme's
    name/tags/summary actually contain one of the expected words;
  * schemes clearly meant for a group the person is not in (ex-servicemen,
    construction-board members, another region ...) are dropped.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from . import localization, scraper
from .profile import FamilyMember, Profile, _f, base_filters

NORTH_EAST = {"Arunachal Pradesh", "Assam", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
              "Sikkim", "Tripura"}

# Words that mark a scheme as meant for one specific group. If the person (or the
# family member a search was for) is not in that group, the scheme is dropped.
GROUP_MARKERS: dict[str, list[str]] = {
    "Farmer": ["kisan", "farmer", "krishi", "fasal"],
    "Ex Servicemen": ["ex-servicem", "ex servicem", "rmewf", "veteran", "war widow"],
    "Construction Worker": ["construction worker", "k.b.o.c.w.w.b", "bocw", "building and other construction"],
    "Journalist": ["journalist"],
    "Lawyer / Law Graduate / Advocate": ["advocate", "lawyer", "law graduate"],
    "Fishermen": ["fisherm", "fisherfolk", "fishing", "fisheries", "matsya", "aquaculture"],
    "Safai Karamchari": ["safai karamchari", "manual scaveng"],
    "Sportsperson": ["sportsperson", "sports person", "athlete", "sportsmen"],
    "Artists": ["artist", "kalakar"],
    "Teacher / Faculty": ["teacher", "faculty"],
    "Artisans, Spinners & Weavers": ["weaver", "handloom", "artisan", "spinner"],
    "Khadi Artisan": ["khadi"],
    "Coir Worker": ["coir"],
    "Street Vendor": ["street vendor"],
    "Health Worker": ["health worker", "asha worker", "anganwadi worker"],
    "Organized Worker": ["employees' pension", "epfo", "employees pension"],
    "_freedom_fighter": ["freedom fighter", "swatantrata sainik"],
    "_transgender": ["transgender"],
    "_north_east": ["north east", "north-east", "northeast", "n.e.r"],
    "_researcher": ["post doctoral", "fellowship", "phd", "researcher"],
    "_tribal": ["janjati", "adivasi", "tribal", "janman"],
    "_award": ["award", "puraskar", "medal", "padma"],
    "_vulnerable_child": ["child protection", "orphan", "juvenile", "vatsalya"],
    "_illness": ["leprosy", "cancer", "hiv", "kidney", "thalassemia", "tuberculosis",
                 "haemophilia", "silicosis"],
    "_organisation": ["voluntary organisation", "voluntary organization", "ngos", "institutions"],
    "_student": ["scholarship", "pre matric", "pre-matric", "post matric", "post-matric",
                 "free coaching", "hostel", "internship"],
}

# Big national and state flagship schemes reach the most people: try them first.
FLAGSHIP_MARKERS = ["pradhan mantri", "pm-", "ayushman", "national", "mukhyamantri",
                    "chief minister", "indira gandhi"]


# Schemes for one crop or trade (coffee growers, exporters ...) are real but niche:
# they rank below broad schemes unless the person mentioned that crop or trade.
NICHE_MARKERS = ["coffee", "coconut", "tea board", "tea development", "rubber", "sericulture", "silk", "spices",
                 "cardamom", "cashew", "jute", "tobacco", "export", "venture capital", "startup",
                 "internship", "fellowship", "awareness", "training of trainers"]


SAFETY_NET = [("health insurance", ["health insurance"]),
              ("accident insurance", ["accident insurance", "suraksha bima"]),
              ("life insurance", ["life insurance", "jeevan jyoti"]),
              ("pension", ["pension"]),
              ("housing", ["housing", "awas"])]


@dataclass
class Query:
    filters: list[dict]
    keyword: str
    weight: float
    reason: str
    member: str = "you"                       # who in the family this search is for
    # Keyword searches only: the hit must contain every word of at least one phrase.
    must_match: list[str] = field(default_factory=list)
    person: Profile | None = None             # whose groups decide "not for you"
    official_occupation: bool = False         # the portal's own job filter was used


@dataclass
class Match:
    slug: str
    item: dict
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    members: list[str] = field(default_factory=list)


def _text(item: dict) -> str:
    return " ".join([item.get("name") or "", item.get("short_title") or "",
                     " ".join(item.get("tags") or []), item.get("brief") or ""]).lower()


def _label(item: dict) -> str:
    """Name and tags only. Group rules use this, because a summary can say the
    opposite ("for workers who are NOT members of EPFO")."""
    return " ".join([item.get("name") or "", item.get("short_title") or "",
                     " ".join(item.get("tags") or [])]).lower()


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(all(w in text for w in ph.split()) for ph in phrases)


COLLEGE_WORDS = ["college", "postgraduate", "post graduate", "post-graduate", "uchchatar",
                 "higher education", "university", "degree", "apprentice", "phd", "post matric", "top class",
                 "post-matric"]
SCHOOL_WORDS = ["pre matric", "pre-matric", "class 9", "class ix", "secondary education"]
# Workers in one named industry; these words are safe to look for in the summary too.
INDUSTRY_WORDS = ["beedi", "cine worker", "non-coal mine", "plantation worker", "tea garden",
                  "coconut tree climber", "toddy"]
OLD_AGE_WORDS = ["old age", "senior citizen", "vridha", "vriddha", "elderly"]


def _school_level(person: Profile) -> str | None:
    """'school' or 'college' for a student, from what they told us (or age as a fallback)."""
    if not person.is_student:
        return None
    edu = (person.education or "").lower()
    if any(w in edu for w in ("college", "degree", "university", "graduat", "diploma", "iti",
                              "nursing", "engineering", "puc", "12th", "class 12")):
        return "college"
    if any(w in edu for w in ("school", "class", "std")) or (person.age is not None and person.age < 16):
        return "school"
    if person.age is not None and person.age >= 18:
        return "college"
    return None


def _not_for(item: dict, person: Profile, state: str | None,
             trust_occupation: bool = False) -> str | None:
    """Return the group a scheme is meant for if the person is not in it, else None.

    trust_occupation: the portal's own occupation filter already says this scheme is
    for the person's job. If the scheme names several kinds of workers (PM-SYM is tagged
    "Artisan, Vendor, Worker" because it covers all unorganised workers), the job-word
    rules are skipped; a scheme for one other job (street vendors) is still dropped.
    """
    text = _label(item)
    name = (item.get("name") or "").lower()
    jobs = [g for g, words in GROUP_MARKERS.items()
            if not g.startswith("_") and any(w in text for w in words)]
    tags = " ".join(item.get("tags") or []).lower()
    broad = len(jobs) >= 2 or any(w in tags for w in ("worker", "labour", "unorganised",
                                                      "unorganized"))   # covers many jobs
    if any(w in _text(item) for w in INDUSTRY_WORDS) and person.occupation != "Organized Worker":
        return "_specific_industry"
    # The portal's age tags are incomplete, so check the obvious cases ourselves.
    if person.age is not None and person.age < 60 and any(w in name for w in OLD_AGE_WORDS):
        return "_senior_citizen"
    level = _school_level(person)
    if level == "school" and any(w in name for w in COLLEGE_WORDS):
        return "_college_student"
    if level == "college" and any(w in name for w in SCHOOL_WORDS):
        return "_school_student"
    for group, words in GROUP_MARKERS.items():
        if not any(w in text for w in words):
            continue
        if group == person.occupation:
            continue
        if trust_occupation and broad and not group.startswith("_"):
            continue
        if group == "Farmer" and person.occupation == "Dairy Farmer":
            continue
        if group == "_tribal" and person.caste in ("Scheduled Tribe (ST)",
                                                   "Particularly Vulnerable Tribal Group (PVTG)"):
            continue
        if group == "_transgender" and person.gender == "Transgender":
            continue
        if group == "_north_east" and state in NORTH_EAST:
            continue
        if group == "Artisans, Spinners & Weavers" and person.occupation == "Khadi Artisan":
            continue
        if group in ("_researcher", "_student") and person.is_student:
            continue
        if group == "_illness" and any(w in " ".join(person.needs).lower() for w in words):
            continue
        return group
    return None


def _kw(base: list[dict], keyword: str, words: list[str], weight: float, reason: str,
        member: str = "you", person: Profile | None = None) -> Query:
    return Query(base, keyword, weight, reason, member, must_match=words, person=person)


def _queries_for_person(p: Profile) -> list[Query]:
    base = base_filters(p)
    qs: list[Query] = []
    occ = p.occupation
    if occ and occ not in ("Homemaker", "Other"):
        qs.append(Query(base + _f("occupation", occ), "", 3, f"For your work: {occ}",
                        official_occupation=True))
    if occ == "Homemaker":
        qs.append(Query(base + _f("gender", "Female"), "", 1.5, "For women"))
    detail = (p.occupation_detail or "").strip().lower()
    if detail.isascii() and detail and detail not in (occ or "").lower():
        # Their own words ("tailor") find schemes the portal's job list misses.
        qs.append(_kw(base, detail, [detail], 3 if occ in (None, "Other") else 2,
                      f"Matches your work: {detail}"))
    if p.is_student:
        qs.append(Query(base + _f("isStudent", "Yes"), "", 3, "For students"))
    if p.has_disability:
        qs.append(Query(base + _f("disability", "Yes"), "", 3, "For persons with disability"))
    if p.is_bpl:
        qs.append(Query(base + _f("isBpl", "Yes"), "", 3, "For BPL card holders"))
    if p.is_minority:
        qs.append(Query(base + _f("minority", "Yes"), "", 2.5, "For minority communities"))
    if p.caste and p.caste not in ("General", "Prefer not to say"):
        qs.append(Query([f for f in base if f["identifier"] != "caste"] + _f("caste", p.caste),
                        "", 2.5, f"For {p.caste.split(' (')[0]} category"))
    if p.gender == "Female":
        qs.append(Query([f for f in base if f["identifier"] != "gender"] + _f("gender", "Female"),
                        "", 2, "For women"))
    if p.age is not None and p.age >= 60:
        qs.append(_kw(base, "old age pension", ["old age", "senior citizen", "elderly"], 2.5,
                      "For senior citizens"))
    if p.marital_status == "Widowed":
        qs.append(_kw(base, "widow", ["widow"], 2.5, "For widows"))
    # Safety net every working-age adult should hear about (insurance, pension, health,
    # housing). Keyword hits must contain the whole phrase; group rules still apply.
    if p.age is None or 18 <= p.age <= 70:
        for kw, words in SAFETY_NET:
            if kw == "housing" and (p.annual_income or 0) > 300000:
                continue
            if kw in (n.lower() for n in p.needs):
                continue                    # they asked for it: searched below at full weight
            qs.append(_kw(base, kw, words, 1.5, f"Basic protection: {kw}"))
    for need in p.needs[:4]:
        # They asked for this themselves, so it outweighs everything else.
        qs.append(_kw(base, need, [need.lower()], 4, f"Matches what you asked for: {need}"))
    return qs


def _person_from_member(p: Profile, m: FamilyMember) -> Profile:
    """A family member inherits the household's state, caste, income and residence."""
    return Profile(state=p.state, residence=p.residence, caste=p.caste,
                   annual_income=p.annual_income, is_bpl=p.is_bpl, is_minority=p.is_minority,
                   age=m.age, gender=m.gender, is_student=m.is_student,
                   education=m.education, occupation=m.occupation,
                   has_disability=m.has_disability, marital_status=m.marital_status,
                   is_gov_employee=False)


def _member_queries(p: Profile, m: FamilyMember) -> list[Query]:
    """Only search for members with something that opens specific schemes."""
    who = m.relation.lower()
    sub = _person_from_member(p, m)
    base = base_filters(sub)
    qs: list[Query] = []
    if m.is_student:
        qs.append(Query(base + _f("isStudent", "Yes"), "", 3, f"For your {who}'s studies", who,
                        person=sub))
    if m.has_disability:
        qs.append(Query(base + _f("disability", "Yes"), "", 3, f"For your {who} (disability)",
                        who, person=sub))
    if m.age is not None and m.age >= 60:
        qs.append(_kw(base, "old age pension", ["old age", "senior citizen", "elderly"], 2.5,
                      f"For your {who} (senior citizen)", who, sub))
    if m.marital_status == "Widowed":
        qs.append(_kw(base, "widow", ["widow"], 2.5, f"For your {who} (widow)", who, sub))
    if m.age is not None and m.age < 6:
        qs.append(_kw(base, "child", ["child", "infant", "nutrition", "anganwadi"], 2,
                      f"For your {who} (young child)", who, sub))
    for need in m.needs[:3]:
        qs.append(_kw(base, need, [need.lower()], 4, f"For your {who}: {need}", who, sub))
    if m.gender == "Female" and m.age is not None and m.age <= 21 and not m.is_student:
        qs.append(_kw(base + _f("gender", "Female"), "girl", ["girl", "daughter", "kanya"], 2,
                      f"For your {who}", who, sub))
    return qs


async def find_schemes(p: Profile, limit: int = 12, per_query: int = 50, language: str = "en") -> dict:
    queries = _queries_for_person(p)
    for m in p.family_members[:6]:
        queries += _member_queries(p, m)
    if not queries:                     # nothing specific known: broad search for the person
        queries.append(Query(base_filters(p), "", 1, "Available where you live"))

    results = await asyncio.gather(*(scraper.search(q.filters, q.keyword, per_query)
                                     for q in queries), return_exceptions=True)

    matches: dict[str, Match] = {}
    errors, dropped = 0, {}
    for q, res in zip(queries, results):
        if isinstance(res, Exception):
            errors += 1
            continue
        person = q.person or p
        for item in res["items"]:
            slug = item.get("slug")
            if not slug or item.get("close_date"):          # skip schemes that have closed
                continue
            if item.get("scheme_for") not in (None, "Individual", "Family"):
                continue                                    # for organisations, not people
            if q.must_match and not _contains_any(_text(item), q.must_match):
                continue                                    # fuzzy keyword hit, not relevant
            group = _not_for(item, person, p.state, q.official_occupation)
            if group:
                dropped[slug] = group
                continue
            m = matches.setdefault(slug, Match(slug=slug, item=item))
            # The portal's own ordering is not a good relevance signal, so every hit that
            # passed the checks above counts fully.
            m.score += q.weight
            if q.reason not in m.reasons:
                m.reasons.append(q.reason)
            if q.member not in m.members:
                m.members.append(q.member)

    mentioned = " ".join([*p.needs, p.occupation_detail or ""]).lower()
    for m in matches.values():
        text = _text(m.item)
        if any(w in text and w not in mentioned for w in NICHE_MARKERS):
            m.score -= 1.0
        name = (m.item.get("name") or "").lower()
        if any(w in name for w in FLAGSHIP_MARKERS):
            m.score += 0.5
        states = m.item.get("states") or []
        if p.state and p.state in states:
            m.score += 0.75
            m.reasons.append(f"A {p.state} state scheme")
        elif m.item.get("level") == "Central":
            m.score += 0.5
            m.reasons.append("Central government scheme, all states")

    ranked = sorted(matches.values(), key=lambda m: m.score, reverse=True)
    # Make sure each family member with a match shows up, not just the speaker...
    chosen: list[Match] = []
    for who in dict.fromkeys(w for m in ranked for w in m.members):
        best = next((m for m in ranked if who in m.members and m not in chosen), None)
        if best:
            chosen.append(best)
    # ...and that one member (e.g. a student with many scholarships) can't crowd out the rest.
    per_member = max(3, limit // 4)
    count = lambda who: sum(1 for c in chosen if c.members[0] == who)   # noqa: E731
    for m in ranked:
        if len(chosen) >= limit:
            break
        if m not in chosen and (m.members[0] == "you" or count(m.members[0]) < per_member):
            chosen.append(m)
    for m in ranked:                    # still room: fill with the best of the rest
        if len(chosen) >= limit:
            break
        if m not in chosen:
            chosen.append(m)
    chosen.sort(key=lambda m: m.score, reverse=True)

    chosen_items = chosen[:limit]
    localized_details = {}
    if language != "en" and chosen_items:
        details = await asyncio.gather(
            *(scraper.detail(m.slug, lang=language) for m in chosen_items),
            return_exceptions=True
        )
        for m, d in zip(chosen_items, details):
            if isinstance(d, dict) and d.get("name"):
                localized_details[m.slug] = d

    schemes_out = []
    for m in chosen_items:
        d = localized_details.get(m.slug) or {}
        eng_name = m.item.get("name")
        loc_title = None

        if d.get("name"):
            loc_title = d.get("name")
        else:
            known = localization.get_known_scheme_title(m.slug, language)
            if known:
                loc_title = known

        if loc_title and loc_title != eng_name:
            if "(" in loc_title:
                display_name = loc_title
            else:
                display_name = f"{loc_title} ({eng_name})" if eng_name else loc_title
            short_title = d.get("short_title") or m.item.get("short_title")
            brief = d.get("brief") or m.item.get("brief")
        else:
            display_name = eng_name
            short_title = m.item.get("short_title")
            brief = m.item.get("brief")

        reasons = [localization.translate_reason(r, language) for r in m.reasons]

        schemes_out.append({
            "slug": m.slug,
            "name": display_name,
            "official_name": eng_name,
            "short_title": short_title,
            "brief": brief,
            "level": d.get("level") or m.item.get("level"),
            "ministry": d.get("ministry") or m.item.get("ministry"),
            "department": d.get("department") or m.item.get("department"),
            "categories": m.item.get("categories"),
            "tags": m.item.get("tags"),
            "for": m.members,
            "why": reasons,
            "score": round(m.score, 2),
            "url": f"{scraper.BASE}/schemes/{m.slug}",
        })

    return {
        "count": len(schemes_out),
        "total_found": len(matches),
        "searched": len(queries),
        "failed_searches": errors,
        "dropped_not_for_you": len(dropped),
        "schemes": schemes_out,
    }
