"""Azure Speech over REST: browser auth tokens, TTS voice notes, and short-audio STT.

The subscription key never leaves the server; the browser only ever gets a 10-minute token.
"""

import re
from xml.sax.saxutils import escape

import httpx

from app import config
from app.models import Model

class SpeechToken(Model):
    token: str
    region: str
    voice: str = config.AZURE_TTS_VOICE_HOUSEHOLD  # browser TTS voice


class SpeechError(RuntimeError):
    pass


def _require_key() -> str:
    if not config.AZURE_SPEECH_KEY:
        raise SpeechError("AZURE_SPEECH_KEY is not set")
    return config.AZURE_SPEECH_KEY


def issue_token() -> SpeechToken:
    """Short-lived token for the browser SDK (the browser reuses it for 9 minutes)."""
    url = f"https://{config.AZURE_SPEECH_REGION}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    response = httpx.post(url, headers={"Ocp-Apim-Subscription-Key": _require_key()}, timeout=10)
    if response.status_code != 200:
        raise SpeechError(f"token request failed: {response.status_code} {response.text[:200]}")
    return SpeechToken(token=response.text, region=config.AZURE_SPEECH_REGION)


def build_ssml(text: str, voice: str, rate: str = "+5%") -> str:
    """One instruction per line becomes a sentence with a short pause after it."""
    lines = [escape(line.strip()) for line in re.split(r"\n+", text) if line.strip()]
    body = '<break time="250ms"/>'.join(lines)
    return (
        f'<speak version="1.0" xml:lang="{config.SPEECH_LANGUAGE}">'
        f'<voice name="{voice}"><prosody rate="{rate}">{body}</prosody></voice>'
        "</speak>"
    )


def _synthesize(text: str, voice: str, audio_format: str) -> bytes:
    url = f"https://{config.AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"
    response = httpx.post(
        url,
        content=build_ssml(text, voice).encode("utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": _require_key(),
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": audio_format,
            "User-Agent": "anyaa-kitchen-agent",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise SpeechError(f"TTS failed: {response.status_code} {response.text[:200]}")
    return response.content


def tts_ogg(text: str, voice: str) -> bytes:
    """Text to OGG/Opus, the format Telegram (and WhatsApp) play as a voice note."""
    return _synthesize(text, voice, "ogg-24khz-16bit-mono-opus")


OGG_OPUS = "audio/ogg; codecs=opus"  # Telegram voice replies


def stt(audio: bytes, language: str = config.SPEECH_LANGUAGE, content_type: str = OGG_OPUS) -> str:
    """Short-audio STT (up to ~60 s), e.g. a cook's Telegram voice reply. Empty string if nothing was heard."""
    url = (
        f"https://{config.AZURE_SPEECH_REGION}.stt.speech.microsoft.com"
        "/speech/recognition/conversation/cognitiveservices/v1"
    )
    response = httpx.post(
        url,
        params={"language": language},
        content=audio,
        headers={
            "Ocp-Apim-Subscription-Key": _require_key(),
            "Content-Type": content_type,
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise SpeechError(f"STT failed: {response.status_code} {response.text[:200]}")
    return response.json().get("DisplayText", "")
