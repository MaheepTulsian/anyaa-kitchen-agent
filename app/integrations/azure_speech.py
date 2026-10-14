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

_token_cache: dict[str, float | str] = {}


class SpeechToken(Model):
    token: str
    region: str
    voice: str = config.AZURE_TTS_VOICE_HOUSEHOLD  # browser TTS voice


class Transcript(Model):
    text: str
    status: str  # Azure RecognitionStatus: Success | NoMatch | InitialSilenceTimeout | ...


class SpeechError(RuntimeError):
    pass


def _require_key() -> str:
    if not config.AZURE_SPEECH_KEY:
        raise SpeechError("AZURE_SPEECH_KEY is not set")
    return config.AZURE_SPEECH_KEY


def issue_token() -> SpeechToken:
    """Short-lived token for the browser SDK. Tokens last 10 min; reuse one for 9."""
    if _token_cache and time.time() < float(_token_cache["expires"]):
        return SpeechToken(token=str(_token_cache["token"]), region=config.AZURE_SPEECH_REGION)

    url = f"https://{config.AZURE_SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    response = httpx.post(url, headers={"Ocp-Apim-Subscription-Key": _require_key()}, timeout=10)
    if response.status_code != 200:
        raise SpeechError(f"token request failed: {response.status_code} {response.text[:200]}")

    _token_cache.update(token=response.text, expires=time.time() + 9 * 60)
    return SpeechToken(token=response.text, region=config.AZURE_SPEECH_REGION)


def _voice_locale(voice: str) -> str:
    """`hi-IN-SwaraNeural` -> `hi-IN`."""
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
