

import { get, post } from '../api.js';
import { el } from '../dom.js';
import { getState } from '../store.js';
import { alert as alertBox, card, emptyState, pageHeader, toast } from '../ui.js';

const STATE_LABELS = {
  pending: 'A determiner',
  lobby: 'A jouer',
  running: 'En cours',
  finished: 'Termine',
  aborted: 'Abandonne',
};

export default async function render(context) {
  const tournamentId = context.params.id;

  let tournament;
  try {
    ({ tournament } = await get(`/api/tournaments/${tournamentId}`));
  } catch (error) {
    return el('div', {}, alertBox(`Tournoi introuvable : ${error.message}`));
  }

  const registering = tournament.state === 'registration';

  return el('div', {},
    pageHeader(tournament.name, {
      subtitle: `${tournament.players.length} joueurs · premier a `
        + `${tournament.points_to_win} points · `
        + (tournament.mode === 'local' ? 'sur un seul clavier' : 'a distance'),
      actions: el('span', {
        class: `badge text-bg-${tournament.state === 'finished' ? 'success' : 'primary'}`,
      }, {
        registration: 'Inscriptions ouvertes',
        running: 'En cours',
        finished: 'Termine',
      }[tournament.state] || tournament.state),
    }),

    registering
      ? registrationPanel(tournament, context)
      : (tournament.winner ? champion(tournament) : nextMatch(tournament)),

    el('div', { class: 'row g-4 mt-1' },
      registering
        ? null
        : el('div', { class: 'col-12 col-lg-8' }, bracketColumn(tournament)),
      el('div', { class: registering ? 'col-12 col-lg-6' : 'col-12 col-lg-4' },
        playersColumn(tournament)),
    ),
  );
}


function registrationPanel(tournament, context) {
  const { user } = getState();
  const registered = user && tournament.players.some((p) => p.user_id === user.id);
  const isOrganiser = user && tournament.created_by_id === user.id;

  const actions = el('div', { class: 'd-flex flex-wrap gap-2' });

  if (!registered) {
    actions.appendChild(action('S’inscrire', 'btn-primary', async () => {
      await post(`/api/tournaments/${tournament.id}/join`, {});
      context.router.navigate(`/tournament/${tournament.id}`);
    }));
  }
  if (isOrganiser) {
    actions.appendChild(action('Lancer le tournoi', 'btn-success', async () => {
      await post(`/api/tournaments/${tournament.id}/start`, {});
      context.router.navigate(`/tournament/${tournament.id}`);
    }, tournament.players.length < 2));
  }

  return el('div', { class: 'card border-primary mb-2' },
    el('div', { class: 'card-body d-flex flex-wrap justify-content-between align-items-center gap-3' },
      el('div', {},
        el('p', { class: 'text-body-secondary mb-1 small text-uppercase' }, 'Inscriptions'),
        el('p', { class: 'mb-0' },
          `${tournament.players.length} joueur${tournament.players.length > 1 ? 's' : ''} `
          + 'inscrit. Le tableau est monte au lancement, une fois tout le monde present.'),
      ),
      actions,
    ),
  );
}

function action(label, variant, handler, disabled = false) {
  return el('button', {
    class: `btn ${variant}`,
    type: 'button',
    disabled: disabled || null,
    onClick: async (event) => {
      event.currentTarget.disabled = true;
      try {
        await handler();
      } catch (error) {
        toast(error.message, 'danger');
        event.currentTarget.disabled = false;
      }
    },
  }, label);
}


function nextMatch(tournament) {
  const match = tournament.next_match;
  if (!match) {
    return el('div', { class: 'alert alert-secondary' },
      'Aucune rencontre a jouer pour le moment.');
  }

  return el('div', { class: 'card border-primary mb-2' },
    el('div', { class: 'card-body d-flex flex-wrap justify-content-between align-items-center gap-3' },
      el('div', {},
        el('p', { class: 'text-body-secondary mb-1 small text-uppercase' },
          `Prochaine rencontre · ${roundNameOf(tournament, match.round_index)}`),
        el('p', { class: 'h4 mb-0' },
          match.players[0].alias,
          el('span', { class: 'text-body-secondary mx-2' }, 'contre'),
          match.players[1].alias),
      ),
      el('a', { class: 'btn btn-primary btn-lg', href: `/game/${match.id}` },
        match.state === 'running' ? 'Reprendre' : 'Jouer ce match'),
    ),
  );
}

function champion(tournament) {
  return el('div', { class: 'card border-success mb-2' },
    el('div', { class: 'card-body text-center' },
      el('p', { class: 'text-body-secondary mb-1 small text-uppercase' }, 'Vainqueur du tournoi'),
      el('p', { class: 'display-6 mb-0' }, tournament.winner.alias),
    ),
  );
}


function bracketColumn(tournament) {
  return card('Tableau',
    el('div', { class: 'd-grid gap-4' },
      tournament.bracket.map((round) => el('section', {},
        el('h3', { class: 'h6 text-uppercase text-body-secondary' }, round.name),
        round.matches.length === 0
          ? el('p', { class: 'form-text mb-0' }, 'Qualifies du tour precedent.')
          : el('div', { class: 'd-grid gap-2' }, round.matches.map(matchRow)),
      )),
    ),
  );
}

function matchRow(match) {
  const finished = match.state === 'finished';
  const winner = match.winner_side;

  const side = (index) => el('div', {
    class: 'flex-grow-1 d-flex justify-content-between gap-2'
      + (finished && winner === index ? ' fw-semibold' : ''),
  },
    el('span', { class: match.players[index].alias ? '' : 'text-body-secondary' },
      match.players[index].alias || 'A determiner'),
    el('span', { class: 'font-monospace' }, finished ? String(match.scores[index]) : '—'),
  );

  const body = el('div', { class: 'flex-grow-1 d-grid gap-1' }, side(0), side(1));

  const action = match.state === 'lobby' || match.state === 'running'
    ? el('a', { class: 'btn btn-sm btn-outline-primary align-self-center', href: `/game/${match.id}` },
      'Jouer')
    : el('span', { class: 'badge text-bg-secondary align-self-center' },
      STATE_LABELS[match.state] || match.state);

  return el('div', {
    class: 'd-flex gap-3 border border-secondary-subtle rounded p-2 align-items-stretch',
  }, body, action);
}


function playersColumn(tournament) {
  if (tournament.players.length === 0) {
    return card('Joueurs', emptyState('Aucun inscrit.'));
  }

  return card('Joueurs',
    el('ol', { class: 'list-unstyled mb-0' },
      tournament.players.map((player, index) => el('li', {
        class: 'd-flex justify-content-between align-items-center py-1'
          + (player.eliminated ? ' text-body-secondary' : ''),
      },
        el('span', {},
          el('span', { class: 'text-body-secondary me-2 font-monospace' }, `${index + 1}.`),
          player.alias),
        player.eliminated
          ? el('span', { class: 'badge text-bg-secondary' }, 'elimine')
          : el('span', { class: 'badge text-bg-primary' }, 'en lice'),
      )),
    ),
  );
}

function roundNameOf(tournament, index) {
  const round = tournament.bracket.find((entry) => entry.index === index);
  return round ? round.name : `Tour ${index + 1}`;
}
