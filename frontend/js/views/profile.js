/**
 * Profil d'un joueur — le sien (`/profile`) ou celui d'un autre (`/users/:id`).
 *
 * Une seule vue pour les deux cas : le contenu est identique, seules les
 * actions changent (modifier son compte / ajouter en ami).
 */

import { del, get, post } from '../api.js';
import { el } from '../dom.js';
import { isOnline, on, seed } from '../live.js';
import { getState } from '../store.js';
import { alert as alertBox, avatar, card, emptyState, pageHeader, toast } from '../ui.js';

export default async function render(context) {
  const own = !context.params.id;
  const { user: me } = getState();

  if (own && !me) {
    context.router.navigate('/login?next=/profile', { replace: true });
    return el('div', {});
  }

  let profile;
  try {
    profile = own
      ? await loadOwnProfile(me)
      : await get(`/api/users/${context.params.id}`);
  } catch (error) {
    return el('div', {}, alertBox(`Profil indisponible : ${error.message}`));
  }

  const { user, stats, history } = profile;
  const statusDot = el('span', { class: 'badge text-bg-secondary' }, '…');

  // Etat initial rapporte par l'API, puis mis a jour en direct par le socket.
  if (user.online) seed([user.id]);

  const refreshStatus = () => {
    const online = own ? true : isOnline(user.id);
    statusDot.textContent = online ? 'En ligne' : 'Hors ligne';
    statusDot.className = `badge text-bg-${online ? 'success' : 'secondary'}`;
  };
  refreshStatus();
  const unsubscribe = on('presence', refreshStatus);

  const node = el('div', {},
    pageHeader(user.display_name, {
      subtitle: user.date_joined
        ? `Inscrit le ${new Date(user.date_joined).toLocaleDateString('fr-FR')}`
        : null,
      actions: own
        ? el('a', { class: 'btn btn-outline-primary', href: '/settings' }, 'Modifier mon compte')
        : friendButton(profile),
    }),

    el('div', { class: 'd-flex align-items-center gap-3 mb-4' },
      avatar(user, 72),
      el('div', {}, statusDot),
    ),

    statsGrid(stats),

    el('h2', { class: 'h5 mt-5 mb-3' }, 'Historique des matchs'),
    historyTable(history),
  );

  return { node, cleanup: unsubscribe };
}

async function loadOwnProfile(me) {
  const data = await get('/api/me/matches');
  return { user: { ...me, online: true }, stats: data.stats, history: data.history };
}

/* --- Statistiques -------------------------------------------------------- */

function statsGrid(stats) {
  const streakLabel = stats.current_streak.count === 0
    ? '—'
    : `${stats.current_streak.count} ${stats.current_streak.type === 'win' ? 'V' : 'D'}`;

  const tiles = [
    ['Matchs joues', stats.played],
    ['Victoires', stats.wins],
    ['Defaites', stats.losses],
    ['Taux de victoire', `${stats.win_rate} %`],
    ['Serie en cours', streakLabel],
    ['Difference de points', formatSigned(stats.points_diff)],
    ['Plus long echange', `${stats.longest_rally} renvois`],
    ['Temps de jeu', formatDuration(stats.playtime_seconds)],
  ];

  return el('div', { class: 'row g-3' },
    tiles.map(([label, value]) => el('div', { class: 'col-6 col-md-3' },
      el('div', { class: 'card h-100' },
        el('div', { class: 'card-body py-3' },
          el('p', { class: 'text-body-secondary small mb-1' }, label),
          el('p', { class: 'h4 mb-0' }, String(value)),
        ),
      ),
    )),
  );
}

function formatSigned(value) {
  return value > 0 ? `+${value}` : String(value);
}

function formatDuration(seconds) {
  if (!seconds) return '—';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}`;
}

/* --- Historique ---------------------------------------------------------- */

function historyTable(history) {
  if (history.length === 0) {
    return card(null, emptyState('Aucun match termine pour l’instant.',
      el('a', { class: 'btn btn-primary', href: '/play' }, 'Jouer une partie')));
  }

  return el('div', { class: 'table-responsive' },
    el('table', { class: 'table table-sm align-middle' },
      el('thead', {},
        el('tr', {},
          el('th', { scope: 'col' }, 'Resultat'),
          el('th', { scope: 'col' }, 'Adversaire'),
          el('th', { scope: 'col' }, 'Score'),
          el('th', { scope: 'col' }, 'Contexte'),
          el('th', { scope: 'col' }, 'Date'),
        ),
      ),
      el('tbody', {}, history.map(historyRow)),
    ),
  );
}

function historyRow(entry) {
  return el('tr', {},
    el('td', {},
      el('span', { class: `badge text-bg-${entry.won ? 'success' : 'secondary'}` },
        entry.won ? 'Victoire' : 'Defaite'),
      entry.by_forfeit ? el('span', { class: 'badge text-bg-warning ms-1' }, 'forfait') : null,
    ),
    el('td', {},
      entry.opponent_id
        ? el('a', { href: `/users/${entry.opponent_id}` }, entry.opponent)
        : entry.opponent,
    ),
    el('td', { class: 'font-monospace' }, `${entry.score[0]} — ${entry.score[1]}`),
    el('td', { class: 'text-body-secondary' },
      entry.tournament
        ? el('a', { href: `/tournament/${entry.tournament_id}` }, entry.tournament)
        : (entry.mode === 'local' ? 'Partie locale' : 'Partie a distance'),
    ),
    el('td', { class: 'text-body-secondary' },
      entry.played_at ? new Date(entry.played_at).toLocaleString('fr-FR', {
        dateStyle: 'short', timeStyle: 'short',
      }) : '—'),
  );
}

/* --- Bouton d'amitie ----------------------------------------------------- */

function friendButton(profile) {
  const { user, friendship } = profile;
  const container = el('div', { class: 'd-flex gap-2' });

  const setContent = (...children) => container.replaceChildren(...children);

  const addButton = () => el('button', {
    class: 'btn btn-primary',
    type: 'button',
    onClick: async (event) => {
      event.currentTarget.disabled = true;
      try {
        await post('/api/friends', { display_name: user.display_name });
        toast('Demande d’ami envoyee.', 'success');
        setContent(el('span', { class: 'badge text-bg-secondary' }, 'Demande envoyee'));
      } catch (error) {
        toast(error.message, 'danger');
        event.currentTarget.disabled = false;
      }
    },
  }, 'Ajouter en ami');

  const removeButton = (id, label) => el('button', {
    class: 'btn btn-outline-secondary',
    type: 'button',
    onClick: async (event) => {
      event.currentTarget.disabled = true;
      try {
        await del(`/api/friends/${id}`);
        setContent(addButton());
      } catch (error) {
        toast(error.message, 'danger');
        event.currentTarget.disabled = false;
      }
    },
  }, label);

  const acceptButton = (id) => el('button', {
    class: 'btn btn-primary',
    type: 'button',
    onClick: async (event) => {
      event.currentTarget.disabled = true;
      try {
        await post(`/api/friends/${id}/accept`, {});
        setContent(removeButton(id, 'Retirer des amis'));
      } catch (error) {
        toast(error.message, 'danger');
        event.currentTarget.disabled = false;
      }
    },
  }, 'Accepter la demande');

  if (!friendship || friendship.status === 'self') return container;
  if (friendship.status === 'none') setContent(addButton());
  else if (friendship.status === 'friends') setContent(removeButton(friendship.id, 'Retirer des amis'));
  else if (friendship.direction === 'incoming') setContent(acceptButton(friendship.id));
  else setContent(removeButton(friendship.id, 'Annuler la demande'));

  return container;
}
