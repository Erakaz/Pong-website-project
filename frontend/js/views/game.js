

import { get } from '../api.js';
import { el } from '../dom.js';
import { KeyboardControls } from '../game/input.js';
import { MatchSocket } from '../game/net.js';
import { PongRenderer } from '../game/renderer.js';
import * as sound from '../game/sound.js';
import { alert as alertBox, pageHeader, toast } from '../ui.js';

const STATUS_LABELS = {
  connecting: 'Connexion…',
  reconnecting: 'Reconnexion…',
  online: 'En ligne',
  offline: 'Connexion perdue',
  closed: 'Deconnecte',
};

export default async function render(context) {
  const matchId = context.params.id;

  let payload;
  try {
    payload = await get(`/api/games/${matchId}`);
  } catch (error) {
    return el('div', {}, alertBox(`Partie introuvable : ${error.message}`));
  }

  const { match, geometry } = payload;


  const scoreLeft = el('span', { class: 'score-value' }, String(match.scores[0]));
  const scoreRight = el('span', { class: 'score-value' }, String(match.scores[1]));


  const liveScore = el('p', {
    class: 'visually-hidden',
    role: 'status',
    'aria-live': 'polite',
  });

  const leftName = el('div', { class: 'player-name' }, match.players[0].alias || 'Joueur 1');
  const rightName = el('div', { class: 'player-name' },
    match.players[1].alias || 'En attente…');

  const scoreboard = el('div', { class: 'scoreboard d-flex justify-content-center align-items-center gap-4 mb-3' },
    el('div', { class: 'text-end flex-grow-1' }, leftName, scoreLeft),
    el('div', { class: 'vs' }, 'vs'),
    el('div', { class: 'text-start flex-grow-1' }, rightName, scoreRight),
  );

  const canvas = el('canvas', {
    class: 'pong-court',
    role: 'img',
    'aria-label': `Terrain de Pong : ${match.players[0].alias} contre `
      + `${match.players[1].alias || 'un adversaire'}`,
  });

  const statusBadge = el('span', { class: 'badge text-bg-secondary' }, STATUS_LABELS.connecting);

  const soundButton = el('button', {
    class: 'btn btn-sm btn-outline-light',
    type: 'button',
    'aria-pressed': String(sound.isEnabled()),
    onClick: (event) => {
      const next = !sound.isEnabled();
      sound.setEnabled(next);
      event.currentTarget.textContent = next ? 'Son ●' : 'Son ○';
      event.currentTarget.setAttribute('aria-pressed', String(next));
    },
  }, sound.isEnabled() ? 'Son ●' : 'Son ○');
  const hint = el('p', { class: 'text-body-secondary text-center small mt-3 mb-0' }, '');
  const banner = el('div', { class: 'd-none' });

  const node = el('div', {},
    pageHeader(match.tournament_id ? 'Match de tournoi' : 'Partie',
      {
        subtitle: `Premier a ${match.points_to_win} point`
          + `${match.points_to_win > 1 ? 's' : ''}.`,
        actions: el('div', { class: 'd-flex align-items-center gap-2' },
          soundButton, statusBadge),
      }),
    banner,
    scoreboard,
    liveScore,
    canvas,
    hint,
  );


  const renderer = new PongRenderer(canvas, geometry);
  let controls = null;
  let lastScores = match.scores.slice();

  const setBanner = (message, variant = 'warning') => {
    banner.replaceChildren(alertBox(message, variant));
    banner.classList.remove('d-none');
  };
  const clearBanner = () => {
    banner.replaceChildren();
    banner.classList.add('d-none');
  };

  const socket = new MatchSocket(matchId, {
    onStatus(status) {
      statusBadge.textContent = STATUS_LABELS[status] || status;
      statusBadge.className = 'badge text-bg-'
        + (status === 'online' ? 'success' : status === 'offline' ? 'danger' : 'secondary');
    },

    onJoined(message) {
      renderer.setGeometry(message.geometry);
      if (message.state) renderer.pushState(message.state);
      renderer.start();

      if (message.replay) {
        setBanner('Cette partie est deja terminee.', 'secondary');
        return;
      }

      if (message.sides.length === 0) {
        hint.textContent = 'Tu regardes cette partie en spectateur.';
        return;
      }

      if (match.mode === 'remote' && !match.players[1].alias) {
        setBanner('En attente d’un adversaire. Partage le lien de cette page, '
          + 'ou attends que quelqu’un rejoigne depuis le salon en ligne.', 'info');
      }

      hint.textContent = KeyboardControls.hint(message.sides);


      if (message.sides.length === 1) renderer.enablePrediction(message.sides[0]);

      controls = new KeyboardControls(message.sides, (side, direction) => {
        socket.sendInput(side, direction);
        if (side === message.sides[0] && message.sides.length === 1) {
          renderer.setDirection(direction);
        }
      });
      controls.attach();
    },

    onState(message) {
      renderer.pushState(message.state);
      updateScores(message.state.scores);
    },

    onPlayer(message) {

      Object.assign(match, message.match);
      leftName.textContent = match.players[0].alias || 'Joueur 1';
      rightName.textContent = match.players[1].alias || 'En attente…';
      if (match.players[1].alias) clearBanner();
    },

    onEvents(message) {
      for (const event of message.events) {


        if (event.type === 'score') renderer.pulse();
        sound.play(event.type === 'serve' ? 'wall' : event.type);
      }
    },

    onOpponent(message) {
      if (message.status === 'left') {
        setBanner(`Ton adversaire s'est deconnecte. Forfait dans `
          + `${message.seconds} secondes s'il ne revient pas.`);
      } else if (message.status === 'back') {
        clearBanner();
        toast('Ton adversaire est de retour.', 'success');
      } else if (message.status === 'forfeit') {
        setBanner('Ton adversaire a abandonne la partie.', 'secondary');
      }
    },

    onEnd(message) {
      renderer.pushState(message.state);
      updateScores(message.state.scores);
      if (controls) {
        controls.detach();
        controls = null;
      }
      showResult(message);
    },

    onAborted() {
      setBanner('Partie abandonnee : plus personne n’etait connecte.', 'secondary');
    },

    onError(message) {
      setBanner(message.message || 'Erreur de partie.', 'danger');
    },
  });

  function updateScores(scores) {
    if (scores[0] === lastScores[0] && scores[1] === lastScores[1]) return;
    lastScores = scores.slice();
    scoreLeft.textContent = String(scores[0]);
    scoreRight.textContent = String(scores[1]);
    liveScore.textContent = `Score : ${match.players[0].alias} ${scores[0]}, `
      + `${match.players[1].alias || 'adversaire'} ${scores[1]}.`;
  }

  function showResult(message) {
    const winnerSide = message.state.winner;
    const winner = winnerSide === null ? null : match.players[winnerSide].alias;
    const stats = message.stats || {};

    const actions = el('div', { class: 'd-flex flex-wrap gap-2 mt-3' },
      match.tournament_id
        ? el('a', { class: 'btn btn-primary', href: `/tournament/${match.tournament_id}` },
          'Retour au tableau')
        : el('a', { class: 'btn btn-primary', href: '/play' }, 'Rejouer'),
    );

    banner.replaceChildren(
      el('div', { class: 'alert alert-success', role: 'alert' },
        el('h2', { class: 'h5 mb-2' }, winner ? `${winner} remporte la partie !` : 'Partie terminee'),
        el('p', { class: 'mb-0' },
          `Score final ${message.state.scores[0]} — ${message.state.scores[1]}`
          + (stats.longest_rally ? ` · plus long echange : ${stats.longest_rally} renvois` : '')
          + (stats.duration_seconds ? ` · duree : ${Math.round(stats.duration_seconds)} s` : '')),
        actions,
      ),
    );
    banner.classList.remove('d-none');
  }

  socket.connect();

  return {
    node,


    cleanup() {
      socket.close();
      renderer.stop();
      sound.dispose();
      if (controls) controls.detach();
    },
  };
}
