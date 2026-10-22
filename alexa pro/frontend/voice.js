/**
 * voice.js — Speech recognition + text-to-speech
 *
 * Exposes a global `Voice` object with:
 *   Voice.init(onResult, onError)
 *   Voice.startListening()
 *   Voice.stopListening()
 *   Voice.speak(text, onEnd)
 *   Voice.stopSpeaking()
 *   Voice.mute() / Voice.unmute()
 *   Voice.isMuted
 *   Voice.populateVoiceList(selectEl)   — fill a <select> with voices
 *   Voice.setRate(n) / Voice.setPitch(n)
 */

window.Voice = (() => {
  // ── State ──────────────────────────────────────────────────────
  let recognition  = null;
  let synth        = window.speechSynthesis;
  let isListening  = false;
  let muted        = false;
  let rate         = 1.0;
  let pitch        = 1.0;
  let preferredVoice = null;

  let audioCtx     = null;
  let analyser     = null;
  let micSource    = null;
  let animFrame    = null;

  let onResultCb   = null;
  let onErrorCb    = null;

  const SpeechRec  = window.SpeechRecognition || window.webkitSpeechRecognition;
  const supported  = !!SpeechRec;

  // ── Init ───────────────────────────────────────────────────────
  function init(onResult, onError) {
    onResultCb = onResult;
    onErrorCb  = onError;

    if (!supported) {
      onErrorCb?.('Speech recognition is not supported in this browser. Use Chrome or Edge for voice features.');
      return;
    }

    setupRecognition();
    prefetchVoices();
  }

  function setupRecognition() {
    recognition = new SpeechRec();
    recognition.continuous     = false;
    recognition.interimResults = true;
    recognition.lang           = 'en-US';
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      isListening = true;
      startAudioAnalysis();
    };

    recognition.onresult = (event) => {
      let interim = '';
      let final_  = '';
      for (const res of event.results) {
        if (res.isFinal) final_ += res[0].transcript;
        else             interim += res[0].transcript;
      }

      // Show interim in transcript area
      const userEl = document.getElementById('transcript-user');
      if (userEl) {
        userEl.textContent = final_ || interim;
        userEl.hidden = false;
      }

      if (final_) {
        onResultCb?.(final_.trim());
      }
    };

    recognition.onerror = (event) => {
      isListening = false;
      stopAudioAnalysis();
      const msg = {
        'no-speech':         'No speech detected. Please try again.',
        'audio-capture':     'Microphone not found. Check your settings.',
        'not-allowed':       'Microphone access denied. Allow it in your browser settings.',
        'network':           'Network error during speech recognition.',
        'aborted':           null,
      }[event.error] || `Recognition error: ${event.error}`;
      if (msg) onErrorCb?.(msg);
    };

    recognition.onend = () => {
      isListening = false;
      stopAudioAnalysis();
      Orb.setState?.('idle');
    };
  }

  // ── Audio analysis (drives orb) ────────────────────────────────
  async function startAudioAnalysis() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioCtx    = new (window.AudioContext || window.webkitAudioContext)();
      analyser    = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      micSource   = audioCtx.createMediaStreamSource(stream);
      micSource.connect(analyser);

      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        if (!isListening) return;
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((s, v) => s + v, 0) / data.length;
        Orb.setAudioLevel?.(avg / 128);
        animFrame = requestAnimationFrame(tick);
      };
      tick();
    } catch (_) {
      // Audio analysis optional — don't block voice
    }
  }

  function stopAudioAnalysis() {
    cancelAnimationFrame(animFrame);
    try { micSource?.disconnect(); audioCtx?.close(); } catch (_) {}
    micSource = null; analyser = null; audioCtx = null;
  }

  // ── Listen ─────────────────────────────────────────────────────
  function startListening() {
    if (!supported) return;
    if (isListening) { stopListening(); return; }

    try {
      recognition.start();
      Orb.setState?.('listening');
    } catch (e) {
      // Already started — rebuild
      setupRecognition();
      try { recognition.start(); Orb.setState?.('listening'); } catch (_) {}
    }
  }

  function stopListening() {
    if (recognition && isListening) {
      recognition.stop();
    }
    isListening = false;
    stopAudioAnalysis();
    Orb.setState?.('idle');
  }

  // ── Speak ──────────────────────────────────────────────────────
  function speak(text, onEnd) {
    if (muted || !text) { onEnd?.(); return; }

    synth.cancel();
    const utter   = new SpeechSynthesisUtterance(text);
    utter.rate    = rate;
    utter.pitch   = pitch;
    if (preferredVoice) utter.voice = preferredVoice;

    utter.onstart = () => Orb.setState?.('speaking');
    utter.onend   = () => { Orb.setState?.('idle'); onEnd?.(); };
    utter.onerror = () => { Orb.setState?.('idle'); onEnd?.(); };

    synth.speak(utter);
  }

  function stopSpeaking() {
    synth.cancel();
    Orb.setState?.('idle');
  }

  // ── Voices ─────────────────────────────────────────────────────
  function prefetchVoices() {
    const load = () => {
      const voices = synth.getVoices();
      // Prefer English US voices
      preferredVoice = voices.find(v => v.lang === 'en-US' && v.name.includes('Google'))
        || voices.find(v => v.lang === 'en-US')
        || voices[0];
    };
    load();
    synth.addEventListener('voiceschanged', load);
  }

  function populateVoiceList(selectEl) {
    if (!selectEl) return;
    const voices = synth.getVoices();
    selectEl.innerHTML = '';
    voices.forEach((v, i) => {
      const opt  = document.createElement('option');
      opt.value  = i;
      opt.text   = `${v.name} (${v.lang})`;
      if (v === preferredVoice) opt.selected = true;
      selectEl.appendChild(opt);
    });
    selectEl.addEventListener('change', () => {
      preferredVoice = synth.getVoices()[parseInt(selectEl.value)];
    });
  }

  // ── Controls ───────────────────────────────────────────────────
  function mute()   { muted = true;  }
  function unmute() { muted = false; }
  function setRate(r)  { rate  = r; }
  function setPitch(p) { pitch = p; }

  return {
    init, startListening, stopListening, speak, stopSpeaking,
    mute, unmute, setRate, setPitch, populateVoiceList,
    get isMuted()     { return muted;       },
    get isListening() { return isListening; },
    get isSupported() { return supported;   },
  };
})();
