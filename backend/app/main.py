"""Scheme Saathi backend.

Flow:
  1. POST /api/transcribe        voice -> text (any Indian language)
  2. POST /api/chat              listen, ask follow-ups, then read back a summary
                                 (repeat until stage == "confirmed")
  3. POST /api/schemes/match     confirmed profile -> matching schemes (official filters)
  4. POST /api/schemes/{slug}/card   flashcard in the user's language, to speak
  5. GET  /api/tts               text -> MP3

No login and no database: the frontend keeps the profile on the phone and
sends it with each request.
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import briefs, conversation, llm, matcher, scraper, tts
from .profile import Language, Profile

app = FastAPI(title="Scheme Saathi API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024


@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm.available(), "last_llm_call": llm.LAST}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty audio")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio too long (max 10 MB)")
    try:
        text = llm.transcribe(data, audio.content_type or "audio/webm")
    except Exception as e:              # noqa: BLE001
        raise HTTPException(502, f"Transcription failed: {e}") from e
    return {"text": text}


@app.post("/api/chat", response_model=conversation.ChatResponse)
def chat(req: conversation.ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Empty message")
    try:
        return conversation.chat(req)
    except Exception as e:              # noqa: BLE001
        raise HTTPException(502, f"Conversation failed: {e}") from e


class MatchRequest(BaseModel):
    profile: Profile
    limit: int = Field(12, ge=1, le=30)
    language: Language = "en"


@app.post("/api/schemes/match")
async def match(req: MatchRequest):
    if not req.profile.state:
        raise HTTPException(400, "Profile needs at least a state")
    return await matcher.find_schemes(req.profile, limit=req.limit, language=req.language)


class CardRequest(BaseModel):
    language: Language = "en"
    profile: Optional[Profile] = None


@app.post("/api/schemes/{slug}/card", response_model=briefs.Card)
async def scheme_card(slug: str, req: CardRequest):
    try:
        return await briefs.card(slug, req.language, req.profile)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@app.get("/api/schemes/{slug}")
async def scheme_detail(slug: str):
    d = await scraper.detail(slug)
    if not d.get("name"):
        raise HTTPException(404, f"Scheme '{slug}' not found")
    return d


@app.get("/api/tts")
def text_to_speech(text: str = Query(..., max_length=1500), lang: str = "en"):
    try:
        return FileResponse(tts.speak(text, lang), media_type="audio/mpeg")
    except Exception as e:              # noqa: BLE001 - frontend falls back to browser voice
        raise HTTPException(502, f"TTS failed: {e}") from e
