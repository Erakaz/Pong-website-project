

import { get } from '../api.js';
import { COLORS, donut, formLines, legend, opponentBars } from '../charts.js';
import { el } from '../dom.js';
import { alert as alertBox, card, emptyState, pageHeader } from '../ui.js';

export default async function render(context) {
  const target = context.query.get('user');

  let data;
  try {
    data = await get(`/api/stats/dashboard${target ? `?user=${encodeURIComponent(target)}` : ''}`);
  } catch (error) {
    return el('div', {}, alertBox(error.message));
  }

  const { summary, by_opponent: byOpponent, recent_form: form, history } = data;

  if (summary.played === 0) {
    return el('div', {},
      pageHeader('Statistiques', { subtitle: data.user.display_name }),
      card(null, emptyState('Aucune partie terminee pour l’instant.',
        el('a', { class: 'btn btn-primary', href: '/play' }, 'Jouer une partie'))),
    );
  }

  return el('div', {},
    pageHeader('Statistiques', {
      subtitle: `${data.user.display_name} · ${summary.played} matchs joues`,
      actions: el('a', { class: 'btn btn-outline-primary', href: '/profile' }, 'Mon profil'),
    }),

    el('div', { class: 'row g-4' },
      el('div', { class: 'col-12 col-lg-4' },
        card('Bilan',
          donut(summary.wins, summary.losses),
          el('dl', { class: 'row mb-0 mt-3 small' },
            statLine('Victoires', summary.wins),
            statLine('Defaites', summary.losses),
            statLine('Points marques', summary.points_for),
            statLine('Points encaisses', summary.points_against),
            statLine('Difference', summary.points_diff > 0
              ? `+${summary.points_diff}` : String(summary.points_diff)),
            statLine('Plus long echange', `${summary.longest_rally} renvois`),
          ),
        ),
      ),

      el('div', { class: 'col-12 col-lg-8' },
        card('Evolution des derniers matchs',
          formLines(form) || emptyState('Il faut au moins deux matchs.'),
          legend([['points marques', COLORS.win], ['points encaisses', COLORS.loss]]),
          formTable(form),
        ),
      ),

      el('div', { class: 'col-12' },
        card('Face a face',
          opponentBars(byOpponent) || emptyState('Aucun adversaire enregistre.'),
          legend([['victoires', COLORS.win], ['defaites', COLORS.loss]]),
          opponentTable(byOpponent),
        ),
      ),

      el('div', { class: 'col-12' },
        card('Detail des parties', matchTable(history)),
      ),
    ),
  );
}

function statLine(name, value) {
  return el('div', { class: 'col-12 d-flex justify-content-between' },
    el('dt', { class: 'fw-normal text-body-secondary' }, name),
    el('dd', { class: 'mb-1' }, String(value)),
  );
}

function formTable(form) {
  if (form.length === 0) return null;
  return el('details', { class: 'mt-3' },
    el('summary', { class: 'small text-body-secondary' }, 'Voir les chiffres'),
    el('ul', { class: 'list-unstyled small mt-2 mb-0' },
      form.map((entry) => el('li', {},
        `${entry.won ? 'V' : 'D'} · ${entry.for}—${entry.against} contre ${entry.opponent}`)),
    ),
  );
}

function opponentTable(rows) {
  if (rows.length === 0) return null;
  return el('div', { class: 'table-responsive mt-3' },
    el('table', { class: 'table table-sm mb-0' },
      el('thead', {}, el('tr', {},
        el('th', { scope: 'col' }, 'Adversaire'),
        el('th', { scope: 'col' }, 'Joues'),
        el('th', { scope: 'col' }, 'V'),
        el('th', { scope: 'col' }, 'D'),
        el('th', { scope: 'col' }, 'Ratio'),
      )),
      el('tbody', {}, rows.map((row) => el('tr', {},
        el('td', {}, row.opponent),
        el('td', {}, String(row.played)),
        el('td', {}, String(row.wins)),
        el('td', {}, String(row.losses)),
        el('td', {}, `${row.win_rate} %`),
      ))),
    ),
  );
}

function matchTable(history) {
  if (history.length === 0) return emptyState('Aucune partie.');
  return el('div', { class: 'table-responsive' },
    el('table', { class: 'table table-sm align-middle mb-0' },
      el('thead', {}, el('tr', {},
        el('th', { scope: 'col' }, 'Adversaire'),
        el('th', { scope: 'col' }, 'Score'),
        el('th', { scope: 'col' }, 'Duree'),
        el('th', { scope: 'col' }, 'Plus long echange'),
        el('th', { scope: 'col' }, ''),
      )),
      el('tbody', {}, history.map((entry) => el('tr', {},
        el('td', {}, entry.opponent),
        el('td', { class: 'font-monospace' }, `${entry.score[0]} — ${entry.score[1]}`),
        el('td', {}, `${Math.round(entry.duration_seconds)} s`),
        el('td', {}, `${entry.longest_rally}`),
        el('td', { class: 'text-end' },
          el('a', { class: 'btn btn-sm btn-outline-primary', href: `/match/${entry.id}` },
            'Detail')),
      ))),
    ),
  );
}
