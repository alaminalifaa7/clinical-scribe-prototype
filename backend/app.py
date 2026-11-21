
import os
import json
import uuid
import time
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import httpx

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# ============================================================
# 1. CONFIGURATION
# ============================================================

load_dotenv()

# ElevenLabs Speech-to-Text
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()

ELEVENLABS_STT_MODEL = os.getenv(
    "ELEVENLABS_STT_MODEL",
    "scribe_v3"
)

ELEVENLABS_API_URL = (
    "https://api.elevenlabs.io/v1/speech-to-text"
)

# Ollama
OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434"
).rstrip("/")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen3:8b"
)

# Application
DEMO_MODE = (
    os.getenv("DEMO_MODE", "false").lower() == "true"
)

# Data storage
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

FEEDBACK_FILE = DATA_DIR / "review_feedback.jsonl"


# ============================================================
# 2. LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | %(levelname)s | "
        "%(name)s | %(message)s"
    )
)

logger = logging.getLogger("clinical_scribe")


# ============================================================
# 3. FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Local Clinical Scribe Research Prototype",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# 4. LANGUAGE CONFIGURATION
# ============================================================

LANGUAGE_CODES = {
    "en": "en",
    "english": "en",
    "eng": "en",

    "bn": "bn",
    "bangla": "bn",
    "bengali": "bn",
    "ben": "bn"
}

def call_elevenlabs(raw, filename, content_type, form_data):
    """
    Synchronous multipart upload to ElevenLabs.

    IMPORTANT:
    HTTPX expects form fields as a mapping here,
    not a list of (key, value) tuples.
    """

    logger.info(
        "ELEVENLABS_HTTP_UPLOAD_START | bytes=%d | filename=%s",
        len(raw),
        filename
    )

    # Convert list of tuples to dictionary.
    form_fields = dict(form_data)

    logger.info(
        "ELEVENLABS_FORM_FIELDS | fields=%s",
        list(form_fields.keys())
    )

    with httpx.Client(
        timeout=httpx.Timeout(180.0)
    ) as client:

        response = client.post(
            ELEVENLABS_API_URL,

            headers={
                "xi-api-key": ELEVENLABS_API_KEY
            },

            data=form_fields,

            files={
                "file": (
                    filename,
                    raw,
                    content_type
                )
            }
        )

        logger.info(
            "ELEVENLABS_HTTP_RESPONSE | status=%d",
            response.status_code
        )

        response.raise_for_status()

        return response.json()


def get_language_options(language: Optional[str]):
    """
    Prepare ElevenLabs language configuration.

    Supported modes:
    - English only
    - Bangla only
    - Automatic Bangla/English detection

    For mixed-language conversations, Scribe v3 receives
    both expected languages as secondary language options.
    """

    if not language or language.lower() == "auto":

        return {
            "language_code": None,
            "secondary_languages": ["en", "bn"]
        }

    normalized = LANGUAGE_CODES.get(
        language.lower()
    )

    if not normalized:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported language. "
                "Use auto, en, or bn."
            )
        )

    secondary = (
        "bn" if normalized == "en" else "en"
    )

    return {
        "language_code": normalized,
        "secondary_languages": [secondary]
    }


# ============================================================
# 5. HEALTH CHECK
# ============================================================

@app.get("/api/health")
async def health():

    return {
        "ok": True,
        "application": "clinical-scribe",
        "version": "2.0.0",
        "demo_mode": DEMO_MODE,
        "transcription_provider": "elevenlabs",
        "transcription_model": ELEVENLABS_STT_MODEL,
        "elevenlabs_configured": bool(
            ELEVENLABS_API_KEY
        ),
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL
    }


# ============================================================
# 6. ELEVENLABS SPEECH-TO-TEXT
# ============================================================

@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: Optional[str] = Query(default="auto")
):

    request_id = str(uuid.uuid4())[:8]
    request_start = time.perf_counter()

    logger.info(
        "[%s] TRANSCRIPTION_REQUEST_RECEIVED | "
        "filename=%s | content_type=%s | language=%s",
        request_id,
        Path(file.filename or "unknown").name,
        file.content_type,
        language
    )

    try:

        # ----------------------------------------------------
        # Demo mode
        # ----------------------------------------------------

        if DEMO_MODE:

            logger.info(
                "[%s] DEMO_MODE_ACTIVE",
                request_id
            )

            return {
                "request_id": request_id,
                "text": (
                    "Patient: I've had headaches for about "
                    "three weeks, mostly in the morning. "
                    "Doctor: Do you take any medication? "
                    "Patient: I sometimes take paracetamol, "
                    "but not every day."
                ),
                "language": "en",
                "language_probability": 1.0,
                "segments": [],
                "words": []
            }

        # ----------------------------------------------------
        # Check API configuration
        # ----------------------------------------------------

        if not ELEVENLABS_API_KEY:

            logger.error(
                "[%s] ELEVENLABS_API_KEY_MISSING",
                request_id
            )

            raise HTTPException(
                status_code=503,
                detail=(
                    "ElevenLabs API key is not configured. "
                    "Check backend/.env."
                )
            )

        # ----------------------------------------------------
        # Read audio
        # ----------------------------------------------------

        raw = await file.read()

        if not raw:

            logger.warning(
                "[%s] EMPTY_AUDIO_UPLOAD",
                request_id
            )

            raise HTTPException(
                status_code=400,
                detail="Empty audio upload."
            )

        filename = Path(
            file.filename or "recording.webm"
        ).name

        content_type = (
            file.content_type
            or "application/octet-stream"
        )

        logger.info(
            "[%s] AUDIO_RECEIVED | bytes=%d | filename=%s",
            request_id,
            len(raw),
            filename
        )

        # ----------------------------------------------------
        # Language settings
        # ----------------------------------------------------

        language_options = get_language_options(
            language
        )

        form_data = [
            ("model_id", ELEVENLABS_STT_MODEL),
            ("tag_audio_events", "false"),
            ("diarize", "true"),
            ("timestamps_granularity", "word"),
            ("numbers_format", "digits")
        ]

        if language_options["language_code"]:

            form_data.append(
                (
                    "language_code",
                    language_options["language_code"]
                )
            )

        # Scribe v3 supports secondary language codes.
        for secondary_language in (
            language_options["secondary_languages"]
        ):

            form_data.append(
                (
                    "secondary_language_codes",
                    secondary_language
                )
            )

        logger.info(
            "[%s] ELEVENLABS_REQUEST_STARTING | "
            "model=%s | primary_language=%s | "
            "secondary_languages=%s",
            request_id,
            ELEVENLABS_STT_MODEL,
            language_options["language_code"] or "auto",
            language_options["secondary_languages"]
        )

        # ----------------------------------------------------
        # Submit audio to ElevenLabs
        # ----------------------------------------------------

        api_start = time.perf_counter()

        result = await asyncio.to_thread(
    call_elevenlabs,
    raw,
    filename,
    content_type,
    form_data
)

        api_elapsed = (
            time.perf_counter() - api_start
        )

        # ----------------------------------------------------
        # Extract transcription
        # ----------------------------------------------------

        transcript = (
            result.get("text", "") or ""
        ).strip()

        detected_language = result.get(
            "language_code",
            "unknown"
        )

        language_probability = result.get(
            "language_probability"
        )

        raw_words = result.get(
            "words",
            []
        ) or []

        # ----------------------------------------------------
        # Normalize word-level results
        # ----------------------------------------------------

        words = []

        for word in raw_words:

            words.append({
                "text": word.get("text", ""),
                "start": word.get("start"),
                "end": word.get("end"),
                "type": word.get("type"),
                "speaker_id": word.get("speaker_id")
            })

        # ----------------------------------------------------
        # Create frontend-compatible segments
        # ----------------------------------------------------

        segments = []

        timed_words = [
            word for word in words
            if isinstance(word.get("start"), (int, float))
            and isinstance(word.get("end"), (int, float))
        ]

        if transcript:

            segment_start = (
                min(
                    word["start"]
                    for word in timed_words
                )
                if timed_words else 0
            )

            segment_end = (
                max(
                    word["end"]
                    for word in timed_words
                )
                if timed_words else 0
            )

            segments.append({
                "start": round(segment_start, 2),
                "end": round(segment_end, 2),
                "text": transcript
            })

        # ----------------------------------------------------
        # Diagnostics
        # ----------------------------------------------------

        total_elapsed = (
            time.perf_counter() - request_start
        )

        if not transcript:

            logger.warning(
                "[%s] ELEVENLABS_EMPTY_TRANSCRIPT | "
                "audio_bytes=%d | language=%s",
                request_id,
                len(raw),
                detected_language
            )

        else:

            logger.info(
                "[%s] ELEVENLABS_SUCCESS | "
                "characters=%d | words=%d | "
                "language=%s | language_probability=%s | "
                "api_seconds=%.2f | total_seconds=%.2f",
                request_id,
                len(transcript),
                len(words),
                detected_language,
                language_probability,
                api_elapsed,
                total_elapsed
            )

        return {
            "request_id": request_id,
            "text": transcript,
            "language": detected_language,
            "language_probability": language_probability,
            "segments": segments,
            "words": words
        }

    # --------------------------------------------------------
    # Error handling
    # --------------------------------------------------------

    except HTTPException:
        raise

    except httpx.HTTPStatusError as e:

        status_code = e.response.status_code

        # Log response details for troubleshooting.
        # Never log the API key.
        logger.error(
            "[%s] ELEVENLABS_HTTP_ERROR | "
            "status=%d | response=%s",
            request_id,
            status_code,
            e.response.text[:1500]
        )

        if status_code == 401:

            detail = (
                "ElevenLabs authentication failed. "
                "Check your API key."
            )

        elif status_code == 422:

            detail = (
                "ElevenLabs rejected the audio or request "
                "parameters. Check the backend logs."
            )

        elif status_code == 429:

            detail = (
                "ElevenLabs rate limit or usage limit reached."
            )

        else:

            detail = (
                f"ElevenLabs returned HTTP {status_code}."
            )

        raise HTTPException(
            status_code=502,
            detail=(
                f"{detail} Request ID: {request_id}"
            )
        )

    except httpx.TimeoutException:

        logger.exception(
            "[%s] ELEVENLABS_TIMEOUT",
            request_id
        )

        raise HTTPException(
            status_code=504,
            detail=(
                "ElevenLabs transcription timed out. "
                f"Request ID: {request_id}"
            )
        )

    except httpx.RequestError:

        logger.exception(
            "[%s] ELEVENLABS_CONNECTION_ERROR",
            request_id
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Could not connect to ElevenLabs. "
                f"Request ID: {request_id}"
            )
        )

    except Exception:

        logger.exception(
            "[%s] TRANSCRIPTION_FAILED",
            request_id
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Transcription failed. "
                f"Request ID: {request_id}"
            )
        )

    finally:

        await file.close()

        logger.info(
            "[%s] TRANSCRIPTION_REQUEST_FINISHED | "
            "total_seconds=%.2f",
            request_id,
            time.perf_counter() - request_start
        )


# ============================================================
# 7. CLINICAL ANALYSIS REQUEST
# ============================================================

class AnalyzeRequest(BaseModel):

    transcript: str
    language: str = "auto"


# ============================================================
# 8. CLINICAL FACT EXTRACTION WITH OLLAMA
# ============================================================

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):

    request_id = str(uuid.uuid4())[:8]

    logger.info(
        "[%s] ANALYZE_REQUEST_RECEIVED | "
        "characters=%d | language=%s",
        request_id,
        len(req.transcript),
        req.language
    )

    if not req.transcript.strip():

        raise HTTPException(
            status_code=400,
            detail="Transcript is empty."
        )

    if DEMO_MODE:

        return demo_analysis(req.transcript)

    prompt = f"""
You are an information extraction assistant for a
RESEARCH PROTOTYPE clinical scribe.

Do not diagnose, prescribe, recommend treatment,
or invent facts.

Extract only what is explicitly stated.

The conversation may be Bangla, English, or code-switched.
Preserve original-language evidence quotes.

Return ONLY valid JSON matching this schema:

{{
 "language_observed": "string",
 "soap": {{
   "subjective": "string",
   "objective": "string",
   "assessment": "string",
   "plan": "string"
 }},
 "facts": [
  {{
    "id": "f1",
    "speaker": "patient|doctor|unknown",
    "category": "symptom|history|medication_mentioned|allergy|measurement|test|other",
    "field": "string",
    "value": "string",
    "evidence_quote": "exact short quote from transcript",
    "confidence": "high|medium|low",
    "status": "needs_review|ready",
    "uncertainty_reason": "string"
  }}
 ],
 "clarifications": [
  {{
    "question": "string",
    "reason": "string",
    "related_fact_ids": ["f1"]
  }}
 ],
 "possible_contradictions": [
  {{
    "description": "string",
    "evidence_quotes": ["quote 1", "quote 2"]
  }}
 ],
 "missing_information": ["string"],
 "safety_notes": ["string"]
}}

Rules:

- SOAP assessment must describe only the clinician's
  explicitly stated assessment.
  If none, say "Not stated in conversation."

- SOAP plan must describe only the clinician's
  explicitly stated plan.
  If none, say "Not stated in conversation."

- Do not convert a patient's suspicion into a diagnosis.

- Do not infer that a medication is currently taken
  just because it is mentioned.

- Keep doses, dates, frequency and negation exactly
  as spoken.

- If unclear, mark low confidence and ask a clarification.

- Each fact must have a verbatim evidence_quote.
  If no exact supporting quote exists, do not emit the fact.

- Ask a clarification rather than resolve conflicting
  statements silently.

- Do not suggest diagnosis or treatment.

- Use concise strings.

- Return JSON only, without Markdown fences.

Conversation language: {req.language}

Conversation:

{req.transcript}
"""

    try:

        logger.info(
            "[%s] OLLAMA_REQUEST_STARTING | model=%s",
            request_id,
            OLLAMA_MODEL
        )

        ollama_start = time.perf_counter()

        async with httpx.AsyncClient(
            timeout=180
        ) as client:

            response = await client.post(
                f"{OLLAMA_URL}/api/generate",

                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.1
                    }
                }
            )

            response.raise_for_status()

            raw = response.json().get(
                "response",
                ""
            )

        logger.info(
            "[%s] OLLAMA_RESPONSE_RECEIVED | "
            "characters=%d | elapsed_seconds=%.2f",
            request_id,
            len(raw),
            time.perf_counter() - ollama_start
        )

        data = json.loads(raw)

        logger.info(
            "[%s] ANALYZE_SUCCESS | "
            "facts=%d | clarifications=%d",
            request_id,
            len(data.get("facts", [])),
            len(data.get("clarifications", []))
        )

        return data

    except httpx.ConnectError:

        logger.exception(
            "[%s] OLLAMA_CONNECTION_FAILED",
            request_id
        )

        raise HTTPException(
            status_code=503,
            detail=(
                f"Cannot reach Ollama at {OLLAMA_URL}. "
                f"Start Ollama and check {OLLAMA_MODEL}."
            )
        )

    except httpx.HTTPStatusError:

        logger.exception(
            "[%s] OLLAMA_HTTP_ERROR",
            request_id
        )

        raise HTTPException(
            status_code=502,
            detail="Ollama returned an HTTP error."
        )

    except json.JSONDecodeError:

        logger.exception(
            "[%s] OLLAMA_INVALID_JSON",
            request_id
        )

        raise HTTPException(
            status_code=502,
            detail="Ollama returned invalid JSON."
        )

    except Exception:

        logger.exception(
            "[%s] ANALYZE_FAILED",
            request_id
        )

        raise HTTPException(
            status_code=500,
            detail="Clinical analysis failed."
        )


# ============================================================
# 9. DEMO ANALYSIS
# ============================================================

def demo_analysis(transcript):

    return {
        "language_observed": "English (demo)",

        "soap": {
            "subjective": (
                "Patient reports headaches for approximately "
                "three weeks, mostly in the morning. Patient "
                "sometimes takes paracetamol, but not every day."
            ),

            "objective": (
                "No objective examination findings stated "
                "in the conversation."
            ),

            "assessment": "Not stated in conversation.",

            "plan": "Not stated in conversation."
        },

        "facts": [
            {
                "id": "f1",
                "speaker": "patient",
                "category": "symptom",
                "field": "symptom",
                "value": "Headache",
                "evidence_quote": (
                    "I've had headaches for about three weeks"
                ),
                "confidence": "high",
                "status": "ready",
                "uncertainty_reason": ""
            },

            {
                "id": "f2",
                "speaker": "patient",
                "category": "history",
                "field": "duration",
                "value": "About three weeks",
                "evidence_quote": (
                    "I've had headaches for about three weeks"
                ),
                "confidence": "high",
                "status": "ready",
                "uncertainty_reason": ""
            },

            {
                "id": "f3",
                "speaker": "patient",
                "category": "symptom",
                "field": "pattern",
                "value": "Mostly in the morning",
                "evidence_quote": "mostly in the morning",
                "confidence": "high",
                "status": "ready",
                "uncertainty_reason": ""
            },

            {
                "id": "f4",
                "speaker": "patient",
                "category": "medication_mentioned",
                "field": "medication use",
                "value": (
                    "Sometimes takes paracetamol; not every day"
                ),
                "evidence_quote": (
                    "I sometimes take paracetamol, "
                    "but not every day"
                ),
                "confidence": "medium",
                "status": "needs_review",
                "uncertainty_reason": (
                    "Exact strength, dose and timing were not stated."
                )
            }
        ],

        "clarifications": [
            {
                "question": (
                    "What strength and dose of paracetamol "
                    "do you take, and when did you last take it?"
                ),
                "reason": (
                    "Medication name was mentioned but dose "
                    "and timing were not provided."
                ),
                "related_fact_ids": ["f4"]
            }
        ],

        "possible_contradictions": [],

        "missing_information": [
            "No examination findings were provided.",
            "No clinician assessment or plan was stated."
        ],

        "safety_notes": [
            "Demo output only. Not clinical advice."
        ]
    }


# ============================================================
# 10. FEEDBACK STORAGE
# ============================================================

class FeedbackRequest(BaseModel):

    session_id: str
    fact_id: Optional[str] = None
    action: str
    original_value: Optional[str] = None
    revised_value: Optional[str] = None
    note: Optional[str] = None


@app.post("/api/feedback")
async def feedback(req: FeedbackRequest):

    request_id = str(uuid.uuid4())[:8]

    try:

        # Pydantic v1/v2 compatibility
        if hasattr(req, "model_dump"):
            record = req.model_dump()
        else:
            record = req.dict()

        record["created_at"] = (
            datetime.now(timezone.utc).isoformat()
        )

        with FEEDBACK_FILE.open(
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                ) + "\n"
            )

        logger.info(
            "[%s] FEEDBACK_SAVED | action=%s | fact_id=%s",
            request_id,
            req.action,
            req.fact_id
        )

        return {
            "saved": True,
            "request_id": request_id
        }

    except Exception:

        logger.exception(
            "[%s] FEEDBACK_SAVE_FAILED",
            request_id
        )

        raise HTTPException(
            status_code=500,
            detail="Could not save feedback."
        )
