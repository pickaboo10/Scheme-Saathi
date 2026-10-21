// Turns what the backend returns into what the cards and sheet show.
//
//   POST /api/schemes/match -> { schemes: [{slug, name, short_title, brief, categories, tags,
//                                           for: ['you','daughter'], why: [...], score, url}], ... }
//   POST /api/schemes/{slug}/card -> { brief: {title, one_line, benefit, who_can_get,
//                                              how_to_apply, documents[], spoken}, apply_url, source_url, backend }

/** Icon for each profile field Saathi might ask about (ChatResponse.asking_about). */
export const ICON_FOR = {
  state: 'map-pin', age: 'clock', gender: 'person', occupation: 'office', residence: 'home',
  annual_income: 'rupee', family_members: 'person', caste: 'person', land_acres: 'land-record',
  is_bpl: 'ration-card',
};

export const CATEGORY_STYLE = {
  farming: { icon: 'farming', disc: 'bg-field-100', ink: 'text-field-800' },
  soil: { icon: 'soil', disc: 'bg-field-100', ink: 'text-field-800' },
  insurance: { icon: 'insurance', disc: 'bg-sky-100', ink: 'text-ink' },
  loans: { icon: 'loans', disc: 'bg-turmeric-100', ink: 'text-ink' },
  pension: { icon: 'pension', disc: 'bg-turmeric-100', ink: 'text-ink' },
  health: { icon: 'health', disc: 'bg-terracotta-100', ink: 'text-terracotta-600' },
  housing: { icon: 'housing', disc: 'bg-terracotta-100', ink: 'text-terracotta-600' },
  general: { icon: 'person', disc: 'bg-turmeric-100', ink: 'text-ink' },
};

/** The portal's categories are many; the design has seven picture groups. */
export function categoryOf(s) {
  const text = [...(s.categories || []), ...(s.tags || []), s.name || ''].join(' ').toLowerCase();
  if (/health|hospital|medical|ayushman|wellness/.test(text)) return 'health';
  if (/housing|awas|shelter|\bhouse\b/.test(text)) return 'housing';
  if (/insurance|bima/.test(text)) return 'insurance';
  if (/soil/.test(text)) return 'soil';
  if (/agri|farm|kisan|crop|fasal|horticult|dairy|animal husbandry|fisher/.test(text)) return 'farming';
  if (/pension|old age|elderly|senior|widow/.test(text)) return 'pension';
  if (/loan|credit|finance|financial|bank|mudra|entrepreneur|business/.test(text)) return 'loans';
  return 'general';
}

/** 'strong' only when it was found for the speaker themselves and several searches agreed. */
export const strengthOf = (s) => ((s.for || []).includes('you') && (s.score || 0) >= 1.75 ? 'strong' : 'maybe');

/** Main matches are for the speaker; "you may also get these" are for family members. */
export function splitResults(schemes) {
  const main = schemes.filter((s) => (s.for || []).includes('you'));
  if (!main.length) return { main: schemes, related: [] };
  return { main, related: schemes.filter((s) => !(s.for || []).includes('you')) };
}

const clip = (text, max) => {
  const t = (text || '').replace(/\s+/g, ' ').trim();
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t;
};

/** Everything a SchemeCard needs. `card` is the localised flashcard if it has loaded. */
export function schemeView(s, card, lang) {
  const brief = card?.brief;
  const title = brief?.title || s.short_title || s.name || s.slug;
  const benefit = clip(brief?.one_line || brief?.benefit || s.brief, 140);
  const official = s.official_name || card?.official_name || s.name;
  const hasIndic = /[^\x00-\x7F]/.test(`${title} ${benefit}`);
  const listenLang = (lang && lang !== 'en' && hasIndic) ? lang : 'en';

  return {
    slug: s.slug,
    category: categoryOf(s),
    strength: strengthOf(s),
    title,
    official,
    benefit,
    why: (s.why || [])[0] || '',
    listenLang,
    translationStatus: card?.translation_status || (hasIndic ? 'verified' : 'fallback_english'),
  };
}

const DOC_RULES = [
  [/aadhaar|aadhar|आधार/i, 'aadhaar'],
  [/bank|passbook|account|पासबुक|बैंक|खाता/i, 'passbook'],
  [/land|khatauni|khasra|7\/12|patta|record|ज़मीन|जमीन|खतौनी|खसरा|भूमि/i, 'land-record'],
  [/ration|राशन/i, 'ration-card'],
  [/photo|picture|फोटो|फ़ोटो/i, 'photo'],
];
export const docIcon = (label) => DOC_RULES.find(([re]) => re.test(label))?.[1] || 'document';

/** "A. B. C." -> ["A.", "B.", "C."] so long answers read as short bullets. */
export const sentences = (text) =>
  (text || '').split(/(?<=[.।!?])\s+/).map((x) => x.trim()).filter(Boolean);

export const hostOf = (url) => {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
};

export function whatsappUrl({ title, benefit, docs, url }, t) {
  const lines = [title, benefit, docs.length ? `${t.docs}: ${docs.join(', ')}` : '', url].filter(Boolean);
  return `https://wa.me/?text=${encodeURIComponent(lines.join('\n'))}`;
}
