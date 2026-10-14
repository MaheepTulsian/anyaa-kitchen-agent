"""Azure Speech over REST: browser auth tokens, TTS, and short-audio STT.

The subscription key never leaves the server; the browser only ever gets a 10-minute token.
"""

import re
import time
import uuid
from xml.sax.saxutils import escape

import httpx

from app import config
from app.models import Model

AUDIO_DIR = config.WEB_DIR / "audio"
TOKEN_TTL_SECONDS = 9 * 60  # Azure tokens last 10 min; refresh a minute early


class SpeechToken(Model):
    token: str
    region: str
    voice: str = config.AZURE_TTS_VOICE_HOUSEHOLD  # browser TTS voice


class Transcript(Model):
    text: str
    status: str  # Azure RecognitionStatus: Success | NoMatch | InitialSilenceTimeout | ...


class SpeechError(RuntimeError):
    pass


_cached_token: SpeechToken | None = None
_cached_until = 0.0


def _require_key() -> str:
    if not config.AZURE_SPEECH_KEY:
        raise SpeechError("AZURE_SPEECH_KEY is not set")
    return config.AZURE_SPEECH_KEY


def issue_token() -> SpeechToken:
    """Short-lived token for the browser SDK, reused until shortly before it expires."""
    global _cached_token, _cached_until
    if _cached_token and time.time() < _cached_until:
        return _cached_token

    url = f"https://{config.AZURE_SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    response = httpx.post(url, headers={"Ocp-Apim-Subscription-Key": _require_key()}, timeout=10)
    if response.status_code != 200:
        raise SpeechError(f"token request failed: {response.status_code} {response.text[:200]}")

    _cached_token = SpeechToken(token=response.text, region=config.AZURE_SPEECH_REGION)
    _cached_until = time.time() + TOKEN_TTL_SECONDS
    return _cached_token


def _voice_locale(voice: str) -> str:
    """`en-IN-NeerjaNeural` -> `en-IN`."""
    return "-".join(voice.split("-")[:2])


def build_ssml(text: str, voice: str, rate: str = "-10%") -> str:
    """One instruction per line becomes a sentence with a short pause after it."""
    lines = [escape(line.strip()) for line in re.split(r"\n+", text) if line.strip()]
    body = '<break time="400ms"/>'.join(lines)
    return (
        f'<speak version="1.0" xml:lang="{_voice_locale(voice)}">'
        f'<voice name="{voice}"><prosody rate="{rate}">{body}</prosody></voice>'
        "</speak>"
    )


def synthesize(text: str, voice: str) -> bytes:
    """Text to a 24 kHz mono WAV."""
    url = f"https://{config.AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
    response = httpx.post(
        url,
        content=build_ssml(text, voice).encode("utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": _require_key(),
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
            "User-Agent": "anyaa-kitchen-agent",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise SpeechError(f"TTS failed: {response.status_code} {response.text[:200]}")
    return response.content


def synthesize_to_file(text: str, voice: str) -> str:
    """Synthesize and save under web/audio; returns the URL path the browser can play."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.wav"
    (AUDIO_DIR / name).write_bytes(synthesize(text, voice))
    return f"/audio/{name}"


def transcribe(wav_16k_mono: bytes, language: str = config.SPEECH_LANGUAGE) -> Transcript:
    """Short-audio STT (up to ~60 s). Expects 16 kHz, 16-bit mono PCM WAV."""
    url = (
        f"https://{config.AZURE_SPEECH_REGION}.stt.speech.microsoft.com"
        "/speech/recognition/conversation/cognitiveservices/v1"
    )
    response = httpx.post(
        url,
        params={"language": language, "format": "simple"},
        content=wav_16k_mono,
        headers={
            "Ocp-Apim-Subscription-Key": _require_key(),
            "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
            "Accept": "application/json",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise SpeechError(f"STT failed: {response.status_code} {response.text[:200]}")
    body = response.json()
    return Transcript(text=body.get("DisplayText", ""), status=body.get("RecognitionStatus", ""))
