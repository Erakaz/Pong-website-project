

import { get } from '../api.js';
import { COLORS, legend, scoreTimeline } from '../charts.js';
import { el } from '../dom.js';
import { alert as alertBox, card, emptyState, pageHeader } from '../ui.js';

export default async function render(context) {
  let data;
  try {
    data = await get(`/api/stats/match/${context.params.id}`);
  } catch (error) {
    return el('div', {}, alertBox(error.message));
  }

  const { match, timeline, summary } = data;
  const names = [match.players[0].alias || 'Joueur 1', match.players[1].alias || 'Joueur 2'];
  const winner = match.winner_side === null ? null : names[match.winner_side];

  return el('div', {},
    pageHeader('Detail de la partie', {
      subtitle: `${names[0]} contre ${names[1]}`
        + (match.finished_at
          ? ` · ${new Date(match.finished_at).toLocaleString('fr-FR')}` : ''),
      actions: el('a', { class: 'btn btn-outline-primary', href: '/dashboard' },
        'Mes statistiques'),
    }),

    el('div', { class: 'row g-4' },
      el('div', { class: 'col-12 col-lg-4' },
        card('Resultat',
          el('p', { class: 'display-6 font-monospace mb-1' },
            `${match.scores[0]} — ${match.scores[1]}`),
          el('p', { class: 'mb-3' },
            winner ? `${winner} l’emporte` : 'Partie sans vainqueur',
            match.by_forfeit
              ? el('span', { class: 'badge text-bg-warning ms-2' }, 'forfait')
              : null),
          el('dl', { class: 'row mb-0 small' },
            line('Duree', `${Math.round(summary.duration_seconds)} s`),
            line('Points joues', summary.points_played),
            line('Renvois au total', summary.total_hits),
            line('Plus long echange', `${summary.longest_rally} renvois`),
            line('Echange moyen', `${summary.average_rally} renvois`),
            line('Mode', match.mode === 'local' ? 'Local' : 'A distance'),
          ),
        ),
      ),

      el('div', { class: 'col-12 col-lg-8' },
        card('Evolution du score',
          scoreTimeline(timeline, names)
            || emptyState('Aucun point enregistre pour cette partie.'),
          legend([[names[0], COLORS.win], [names[1], COLORS.loss]]),
          pointsTable(timeline, names),
        ),
      ),
    ),
  );
}

function line(name, value) {
  return el('div', { class: 'col-12 d-flex justify-content-between' },
    el('dt', { class: 'fw-normal text-body-secondary' }, name),
    el('dd', { class: 'mb-1' }, String(value)),
  );
}

function pointsTable(timeline, names) {
  if (timeline.length === 0) return null;
  return el('details', { class: 'mt-3' },
    el('summary', { class: 'small text-body-secondary' }, 'Voir les points un par un'),
    el('div', { class: 'table-responsive mt-2' },
      el('table', { class: 'table table-sm mb-0' },
        el('thead', {}, el('tr', {},
          el('th', { scope: 'col' }, 'Temps'),
          el('th', { scope: 'col' }, 'Point pour'),
          el('th', { scope: 'col' }, 'Echange'),
          el('th', { scope: 'col' }, 'Score'),
        )),
        el('tbody', {}, timeline.map((point) => el('tr', {},
          el('td', {}, `${point.t} s`),
          el('td', {}, names[point.side]),
          el('td', {}, `${point.rally} renvois`),
          el('td', { class: 'font-monospace' }, point.scores.join(' — ')),
        ))),
      ),
    ),
  );
}
