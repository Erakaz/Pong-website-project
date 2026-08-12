

import { get, post } from '../api.js';
import { clear, el } from '../dom.js';
import { getState } from '../store.js';
import { alert as alertBox, card, emptyState, pageHeader, spinner, toast } from '../ui.js';

const REFRESH_INTERVAL = 4000;

export default async function render(context) {
  const { user } = getState();
  if (!user) {
    context.router.navigate('/login?next=/online', { replace: true });
    return el('div', {});
  }

  const matchList = el('div', { class: 'd-grid gap-2' }, spinner('Recherche de parties…'));
  const tournamentList = el('div', { class: 'd-grid gap-2' }, spinner('Chargement…'));

  const refresh = async () => {
    try {
      const [matches, tournaments] = await Promise.all([
        get('/api/games?mode=remote&state=lobby'),
        get('/api/tournaments'),
      ]);
      paintMatches(matchList, matches.matches, user, context);
      paintTournaments(tournamentList, tournaments.tournaments, user, context);
    } catch (error) {
      clear(matchList);
      matchList.appendChild(alertBox(error.message));
    }
  };

  await refresh();
  const timer = window.setInterval(refresh, REFRESH_INTERVAL);

  const node = el('div', {},
    pageHeader('Jouer en ligne', {
      subtitle: 'Affronte un joueur sur une autre machine, ou rejoins un tournoi.',
      actions: [
        el('button', {
          class: 'btn btn-primary',
          type: 'button',
          onClick: async (event) => {
            event.currentTarget.disabled = true;
            try {
              const { match } = await post('/api/games', { mode: 'remote' });
              context.router.navigate(`/game/${match.id}`);
            } catch (error) {
              toast(error.message, 'danger');
              event.currentTarget.disabled = false;
            }
          },
        }, 'Ouvrir une partie'),
        el('button', {
          class: 'btn btn-outline-primary',
          type: 'button',
          onClick: async (event) => {
            event.currentTarget.disabled = true;
            try {
              const { tournament } = await post('/api/tournaments', { mode: 'remote' });
              context.router.navigate(`/tournament/${tournament.id}`);
            } catch (error) {
              toast(error.message, 'danger');
              event.currentTarget.disabled = false;
            }
          },
        }, 'Ouvrir un tournoi'),
      ],
    }),

    el('div', { class: 'row g-4' },
      el('div', { class: 'col-12 col-lg-6' }, card('Parties ouvertes', matchList)),
      el('div', { class: 'col-12 col-lg-6' }, card('Tournois ouverts', tournamentList)),
    ),
  );


  return { node, cleanup: () => window.clearInterval(timer) };
}

function paintMatches(container, matches, user, context) {
  clear(container);
  if (matches.length === 0) {
    container.appendChild(emptyState('Aucune partie en attente. Ouvre la tienne !'));
    return;
  }

  for (const match of matches) {
    const mine = match.players[0].user_id === user.id;
    container.appendChild(el('div', {
      class: 'd-flex align-items-center gap-3 border border-secondary-subtle rounded p-2',
    },
      el('div', { class: 'flex-grow-1' },
        el('div', {}, match.players[0].alias || 'Joueur'),
        el('small', { class: 'text-body-secondary' },
          `Premier a ${match.points_to_win} points`),
      ),
      mine
        ? el('a', { class: 'btn btn-sm btn-outline-primary', href: `/game/${match.id}` },
          'Ma partie')
        : el('button', {
          class: 'btn btn-sm btn-primary',
          type: 'button',
          onClick: async (event) => {
            event.currentTarget.disabled = true;
            try {
              await post(`/api/games/${match.id}/join`, {});
              context.router.navigate(`/game/${match.id}`);
            } catch (error) {
              toast(error.message, 'danger');
              event.currentTarget.disabled = false;
            }
          },
        }, 'Rejoindre'),
    ));
  }
}

function paintTournaments(container, tournaments, user, context) {
  clear(container);
  if (tournaments.length === 0) {
    container.appendChild(emptyState('Aucun tournoi en cours.'));
    return;
  }

  for (const tournament of tournaments) {
    const registered = tournament.players.some((player) => player.user_id === user.id);
    const open = tournament.state === 'registration';

    container.appendChild(el('div', {
      class: 'd-flex align-items-center gap-3 border border-secondary-subtle rounded p-2',
    },
      el('div', { class: 'flex-grow-1' },
        el('div', {}, tournament.name),
        el('small', { class: 'text-body-secondary' },
          `${tournament.players.length} inscrit${tournament.players.length > 1 ? 's' : ''}`
          + ` · ${open ? 'inscriptions ouvertes' : 'en cours'}`),
      ),
      registered || !open
        ? el('a', { class: 'btn btn-sm btn-outline-primary', href: `/tournament/${tournament.id}` },
          'Voir')
        : el('button', {
          class: 'btn btn-sm btn-primary',
          type: 'button',
          onClick: async (event) => {
            event.currentTarget.disabled = true;
            try {
              await post(`/api/tournaments/${tournament.id}/join`, {});
              context.router.navigate(`/tournament/${tournament.id}`);
            } catch (error) {
              toast(error.message, 'danger');
              event.currentTarget.disabled = false;
            }
          },
        }, 'S’inscrire'),
    ));
  }
}
