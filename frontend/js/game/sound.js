/**
 * Bips du Pong de 1972, synthetises.
 *
 * La borne d'origine n'avait pas de sons enregistres : trois tonalites etaient
 * derivees du signal de synchronisation vertical de l'ecran, ce qui donnait
 * des ondes carrees courtes et seches. On refait la meme chose avec Web Audio
 * — aucun fichier a telecharger, et le resultat est fidele.
 *
 * Les frequences ci-dessous sont celles couramment relevees sur la borne :
 * un son grave pour les murs, un plus aigu pour les raquettes, un troisieme,
 * plus long, pour le point marque.
 *
 * Le navigateur interdit de produire du son avant une interaction de
 * l'utilisateur. Le contexte audio est donc cree paresseusement, au premier
 * evenement de jeu — qui suit toujours un clic sur « Jouer ».
 */

const TONES = {
  wall:   { frequency: 226, duration: 0.016 },
  hit:    { frequency: 459, duration: 0.016 },
  score:  { frequency: 490, duration: 0.24 },
};

const STORAGE_KEY = 'ftt_sound';

let context = null;
let master = null;

/** Le reglage survit au rechargement ; c'est une preference, pas une session. */
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
  if (!AudioContextClass) return null;          // navigateur sans Web Audio

  try {
    context = new AudioContextClass();
  } catch {
    return null;
  }

  master = context.createGain();
  // Volume volontairement bas : ces bips sont percants, et personne ne veut
  // sursauter en ouvrant une partie.
  master.gain.value = 0.06;
  master.connect(context.destination);
  return context;
}

/**
 * Joue une des trois tonalites.
 * @param {'wall'|'hit'|'score'} kind
 */
export function play(kind) {
  const tone = TONES[kind];
  if (!tone || !isEnabled()) return;

  const audio = ensureContext();
  if (!audio) return;

  // Le contexte demarre suspendu tant qu'aucune interaction n'a eu lieu.
  if (audio.state === 'suspended') audio.resume().catch(() => {});

  const oscillator = audio.createOscillator();
  const envelope = audio.createGain();

  oscillator.type = 'square';                    // l'onde de la borne d'origine
  oscillator.frequency.value = tone.frequency;

  // Coupure nette plutot qu'un fondu : un arret brutal produirait un clic
  // audible, mais une descente trop douce sonnerait moderne. Quelques
  // millisecondes suffisent.
  const now = audio.currentTime;
  envelope.gain.setValueAtTime(1, now);
  envelope.gain.setValueAtTime(1, now + tone.duration);
  envelope.gain.linearRampToValueAtTime(0, now + tone.duration + 0.008);

  oscillator.connect(envelope);
  envelope.connect(master);
  oscillator.start(now);
  oscillator.stop(now + tone.duration + 0.02);
}

/** Libere le contexte audio quand on quitte la partie. */
export function dispose() {
  if (!context) return;
  context.close().catch(() => {});
  context = null;
  master = null;
}
