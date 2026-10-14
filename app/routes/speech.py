"""Speech endpoints: browser token, server TTS (cook voice notes), server STT (cook replies)."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from app import config
from app.integrations import azure_speech
from app.integrations.azure_speech import SpeechError, SpeechToken, Transcript
from app.models import Model

router = APIRouter(prefix="/api/speech")

VOICES = {
    "household": config.AZURE_TTS_VOICE_HOUSEHOLD,
    "cook": config.AZURE_TTS_VOICE_COOK,
}


class TtsRequest(Model):
    text: str
    who: Literal["household", "cook"] = "cook"


class TtsResponse(Model):
    audio_url: str


@router.get("/token")
def speech_token() -> SpeechToken:
    try:
        return azure_speech.issue_token()
    except SpeechError as error:
        raise HTTPException(503, str(error)) from error


@router.post("/tts")
def text_to_speech(body: TtsRequest) -> TtsResponse:
    try:
        return TtsResponse(audio_url=azure_speech.synthesize_to_file(body.text, VOICES[body.who]))
    except SpeechError as error:
        raise HTTPException(503, str(error)) from error


@router.post("/stt")
async def speech_to_text(request: Request, language: str = config.SPEECH_LANGUAGE) -> Transcript:
    """Body is a raw 16 kHz mono WAV (the browser recorder produces this)."""
    audio = await request.body()
    if not audio:
        raise HTTPException(400, "empty audio body")
    try:
        return azure_speech.transcribe(audio, language)
    except SpeechError as error:
        raise HTTPException(503, str(error)) from error
