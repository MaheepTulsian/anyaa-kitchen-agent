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

// Speaks text sentence by sentence as it streams in. feed() takes deltas; flush() speaks the rest.
export class Speaker {
  constructor() {
    this.muted = false;
    this.buffer = "";
    this.synth = null;
  }

  async #synth() {
    if (!this.synth) {
      const cfg = await speechConfig("en-IN");
      this.synth = new SpeechSDK.SpeechSynthesizer(
        cfg,
        SpeechSDK.AudioConfig.fromDefaultSpeakerOutput(),
      );
    }
    return this.synth;
  }

  async say(text) {
    const clean = cleanForSpeech(text);
    if (this.muted || !clean) return;
    const synth = await this.#synth();
    synth.speakTextAsync(clean, () => {}, (err) => console.error("TTS", err));
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
    if (this.synth) {
      this.synth.close();
      this.synth = null;
    }
  }

  setMuted(muted) {
    this.muted = muted;
    if (muted) this.stop();
  }
}
