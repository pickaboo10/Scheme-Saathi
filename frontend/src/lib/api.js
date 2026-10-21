// Client for the Scheme Saathi backend (backend/app/main.py).
//
// Every failure becomes an ApiError with a `kind` the UI knows how to explain in plain words:
//   offline     can't reach the server at all (no internet, server down, proxy error)
//   timeout     the request took too long (slow internet, or Gemini retrying)
//   busy        backend answered 502/429: Gemini is rate-limited or failed (free tier ~8-10 calls/min)
//   too-long    413: the voice recording is over 10 MB
//   not-found   404: unknown scheme
//   bad-request 400/422: empty message/audio, or a payload the backend rejects
//   error       anything else
export const API_BASE_URL = (
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE ||
  (import.meta.env.PROD ? 'https://scheme-saathi-api-z385.onrender.com' : '')
).trim().replace(/\/+$/, '');

const BASE = API_BASE_URL;

const buildUrl = (path) => {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${BASE}${cleanPath}`;
};


export class ApiError extends Error {
  constructor(kind, status = 0, detail = '') {
    super(detail || kind);
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }
}

function classify(status, body, rawText) {
  const detail = typeof body?.detail === 'string' ? body.detail : Array.isArray(body?.detail) ? 'invalid request' : '';
  if (status === 413) return new ApiError('too-long', status, detail);
  if (status === 404) return new ApiError('not-found', status, detail);
  if (status === 400 || status === 422) return new ApiError('bad-request', status, detail);
  if (status === 429) return new ApiError('busy', status, detail);
  if (status >= 500) {
    // The backend always sends {detail} for the failures it expects (502 = Gemini failed).
    if (body?.detail != null) return new ApiError('busy', status, detail);
    // A gateway/proxy error page, or an empty body (Vite proxy with the backend down): unreachable.
    if (!rawText || /^\s*</.test(rawText) || status !== 500) return new ApiError('offline', status);
    return new ApiError('error', status, rawText.slice(0, 120)); // FastAPI "Internal Server Error"
  }
  return new ApiError('error', status, detail);
}

async function request(path, { method = 'GET', json, form, timeout = 45000 } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  let res;
  try {
    res = await fetch(buildUrl(path), {
      method,
      headers: json ? { 'content-type': 'application/json' } : undefined,
      body: json ? JSON.stringify(json) : form,
      signal: ctl.signal,
    });
  } catch (e) {
    clearTimeout(timer);
    throw new ApiError(e?.name === 'AbortError' ? 'timeout' : 'offline');
  }
  let raw = '';
  try { raw = await res.text(); } catch { /* connection dropped mid-body */ }
  clearTimeout(timer);
  let body = null;
  try { body = raw ? JSON.parse(raw) : null; } catch { /* not JSON */ }
  if (!res.ok) throw classify(res.status, body, raw);
  if (body == null) throw new ApiError('error', res.status, 'empty response');
  return body;
}

const baseMime = (type) => (type || 'audio/webm').split(';')[0];
const extFor = (mime) => (mime.includes('mp4') ? 'm4a' : mime.includes('ogg') ? 'ogg' : mime.includes('wav') ? 'wav' : 'webm');

export const api = {
  health: () => request('/api/health', { timeout: 8000 }),

  /** Voice -> { text } in the speaker's own script. */
  transcribe(blob) {
    const mime = baseMime(blob.type);
    const form = new FormData();
    form.append('audio', new File([blob], `speech.${extFor(mime)}`, { type: mime }));
    return request('/api/transcribe', { method: 'POST', form, timeout: 60000 });
  },

  /** One conversation turn. The caller keeps the state and sends it back each time. */
  chat: ({ message, stage, profile, asked, history, language }) =>
    request('/api/chat', {
      method: 'POST',
      json: { message, stage, profile, asked, history, language },
      timeout: 60000,
    }),

  match: (profile, limit = 12, language = 'en') =>
    request('/api/schemes/match', { method: 'POST', json: { profile, limit, language }, timeout: 60000 }),

  card: (slug, language, profile) =>
    request(`/api/schemes/${encodeURIComponent(slug)}/card`, {
      method: 'POST',
      json: { language, profile },
      timeout: 60000,
    }),

  ttsUrl: (text, lang) => `${buildUrl('/api/tts')}?text=${encodeURIComponent(text)}&lang=${encodeURIComponent(lang)}`,
};

/** Which StatusBanner explains this failure, and whether "Try again" makes sense. */
export function bannerFor(err) {
  switch (err?.kind) {
    case 'offline': return { kind: 'offline', retry: true };
    case 'timeout': return { kind: 'slow', retry: true };
    case 'busy': return { kind: 'busy', retry: true };
    case 'too-long': return { kind: 'too-long', retry: false };
    default: return { kind: 'error', retry: true };
  }
}
