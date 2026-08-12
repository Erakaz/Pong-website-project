

const TONES = {
  wall:   { frequency: 226, duration: 0.016 },
  hit:    { frequency: 459, duration: 0.016 },
  score:  { frequency: 490, duration: 0.24 },
};

const STORAGE_KEY = 'ftt_sound';

let context = null;
let master = null;


export function isEnabled() {
  return window.localStorage.getItem(STORAGE_KEY) !== 'off';
}

export function setEnabled(enabled) {
  window.localStorage.setItem(STORAGE_KEY, enabled ? 'on' : 'off');
  if (!enabled && context) context.suspend().catch(() => {});
}

function ensureContext() {
  if (context) return context;

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return null;

  try {
    context = new AudioContextClass();
  } catch {
    return null;
  }

  master = context.createGain();


  master.gain.value = 0.06;
  master.connect(context.destination);
  return context;
}


export function play(kind) {
  const tone = TONES[kind];
  if (!tone || !isEnabled()) return;

  const audio = ensureContext();
  if (!audio) return;


  if (audio.state === 'suspended') audio.resume().catch(() => {});

  const oscillator = audio.createOscillator();
  const envelope = audio.createGain();

  oscillator.type = 'square';
  oscillator.frequency.value = tone.frequency;


  const now = audio.currentTime;
  envelope.gain.setValueAtTime(1, now);
  envelope.gain.setValueAtTime(1, now + tone.duration);
  envelope.gain.linearRampToValueAtTime(0, now + tone.duration + 0.008);

  oscillator.connect(envelope);
  envelope.connect(master);
  oscillator.start(now);
  oscillator.stop(now + tone.duration + 0.02);
}


export function dispose() {
  if (!context) return;
  context.close().catch(() => {});
  context = null;
  master = null;
}
