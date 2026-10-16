// Household voice I/O in the browser via the Azure Speech JS SDK (global `SpeechSDK`).
// The server hands out a 10-minute token; the subscription key never reaches the browser.

let auth = null; // { token, region, voice, fetchedAt }

async function getAuth() {
  if (auth && Date.now() - auth.fetchedAt < 9 * 60 * 1000) return auth;
  const res = await fetch("/api/speech/token");
  if (!res.ok) throw new Error(`speech token: ${(await res.json()).detail}`);
  auth = { ...(await res.json()), fetchedAt: Date.now() };
  return auth;
}

async function speechConfig(language) {
  const { token, region, voice } = await getAuth();
  const cfg = SpeechSDK.SpeechConfig.fromAuthorizationToken(token, region);
  cfg.speechRecognitionLanguage = language;
  cfg.speechSynthesisVoiceName = voice;
  return cfg;
}

// Push-to-talk listener. start() opens the mic; stop() closes it and resolves with the full text.
export class Listener {
  constructor({ language = "en-IN", phrases = [], onInterim = () => {} } = {}) {
    this.language = language;
    this.phrases = phrases;
    this.onInterim = onInterim;
    this.recognizer = null;
    this.finalParts = [];
  }

  async start() {
    const cfg = await speechConfig(this.language);
    const audio = SpeechSDK.AudioConfig.fromDefaultMicrophoneInput();
    this.recognizer = new SpeechSDK.SpeechRecognizer(cfg, audio);
    this.finalParts = [];

    // Bias recognition toward dish and ingredient names ("rajma", "karela", "sabudana").
    if (this.phrases.length) {
      SpeechSDK.PhraseListGrammar.fromRecognizer(this.recognizer).addPhrases(this.phrases);
    }

    this.recognizer.recognizing = (_, e) => {
      this.onInterim([...this.finalParts, e.result.text].join(" "));
    };
    this.recognizer.recognized = (_, e) => {
      if (e.result.reason === SpeechSDK.ResultReason.RecognizedSpeech && e.result.text) {
        this.finalParts.push(e.result.text);
        this.onInterim(this.finalParts.join(" "));
      }
    };

    await new Promise((resolve, reject) =>
      this.recognizer.startContinuousRecognitionAsync(resolve, reject),
    );
  }

  async stop() {
    if (!this.recognizer) return "";
    const recognizer = this.recognizer;
    this.recognizer = null;
    await new Promise((resolve, reject) =>
      recognizer.stopContinuousRecognitionAsync(resolve, reject),
    );
    recognizer.close();
    return this.finalParts.join(" ").trim();
  }
}

// Strip anything a voice should not read out: markdown, bullets, emojis.
function cleanForSpeech(text) {
  return text
    .replace(/[*_`#>|]/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/\p{Extended_Pictographic}/gu, "")
    .trim();
}

// Natural speaking pace for Anyaa. Azure's default reads slow for a quick, chatty character.
const RATE = "+15%";

function escapeXml(text) {
  return text.replace(/[<>&'"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" })[c]);
}

// Speaks Anyaa's replies. say() speaks a whole reply in one request (no gaps between sentences);
// feed()/flush() speak streamed text sentence by sentence (used by the voice lab).
export class Speaker {
  constructor() {
    this.muted = false;
    this.buffer = "";
    this.synth = null; // Promise<SpeechSynthesizer>, shared by everything we say
    this.synthAt = 0; // when it was created; Azure tokens expire after 10 minutes
    this.queue = Promise.resolve(); // replies are spoken strictly one after another
  }

  #synth() {
    // Keep the promise, not the result, so replies arriving together share one synthesizer and
    // never talk over each other. Rebuild it before the token expires.
    if (!this.synth || Date.now() - this.synthAt > 9 * 60 * 1000) {
      this.#drop();
      this.synthAt = Date.now();
      this.synth = speechConfig("en-IN").then((cfg) => {
        const synth = new SpeechSDK.SpeechSynthesizer(cfg, SpeechSDK.AudioConfig.fromDefaultSpeakerOutput());
        SpeechSDK.Connection.fromSynthesizer(synth).openConnection(); // connect now, not on the first word
        return synth;
      });
    }
    return this.synth;
  }

  #drop() {
    this.synth?.then((s) => s.close()).catch(() => {});
    this.synth = null;
  }

  // Get the token and the connection ready before Anyaa's first reply.
  warm() {
    this.#synth().catch(() => this.#drop());
  }

  say(text) {
    const clean = cleanForSpeech(text);
    if (this.muted || !clean) return this.queue;
    this.queue = this.queue.then(async () => {
      try {
        const synth = await this.#synth();
        const { voice } = await getAuth();
        const ssml = `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-IN">` +
          `<voice name="${voice}"><prosody rate="${RATE}">${escapeXml(clean)}</prosody></voice></speak>`;
        const result = await new Promise((resolve, reject) => synth.speakSsmlAsync(ssml, resolve, reject));
        if (result.reason === SpeechSDK.ResultReason.Canceled) throw new Error(result.errorDetails);
      } catch (err) {
        console.error("TTS", err); // a failed reply never blocks the next one
        this.#drop(); // and the next one gets a fresh synthesizer and token
      }
    });
    return this.queue;
  }

  feed(delta) {
    this.buffer += delta;
    // Split after . ? ! or the Hindi danda, keeping any unfinished tail in the buffer.
    const parts = this.buffer.split(/(?<=[.?!।])\s+/);
    this.buffer = parts.pop();
    parts.forEach((sentence) => this.say(sentence));
  }

  flush() {
    const rest = this.buffer;
    this.buffer = "";
    return this.say(rest);
  }

  stop() {
    this.buffer = "";
    this.queue = Promise.resolve();
    this.#drop();
  }

  setMuted(muted) {
    this.muted = muted;
    if (muted) this.stop();
  }
}
