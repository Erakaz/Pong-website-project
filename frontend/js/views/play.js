

import { post } from '../api.js';
import { el } from '../dom.js';
import { getState } from '../store.js';
import { applyFormError, card, field, pageHeader } from '../ui.js';

const MIN_PLAYERS = 2;
const MAX_PLAYERS = 16;

export default function render(context) {
  const node = el('div', {},
    pageHeader('Jouer', {
      subtitle: 'Partie rapide a deux sur le meme clavier, ou tournoi a elimination directe.',
    }),
    el('div', { class: 'row g-4 align-items-start' },
      el('div', { class: 'col-12 col-lg-6' }, localMatchForm(context)),
      el('div', { class: 'col-12 col-lg-6' }, tournamentForm(context)),
    ),
  );
  return node;
}


function localMatchForm(context) {
  const { user } = getState();

  const fields = {
    alias1: field('alias1', 'Joueur de gauche', {
      value: user ? user.display_name : 'Joueur 1',
      autocomplete: 'off',
      maxlength: 16,
    }),
    alias2: field('alias2', 'Joueur de droite', {
      value: 'Joueur 2',
      autocomplete: 'off',
      maxlength: 16,
    }),
  };

  const points = pointsSelect('points-local');
  const banner = el('div', { class: 'alert alert-danger d-none', role: 'alert' });
  const submit = el('button', { class: 'btn btn-primary w-100', type: 'submit' },
    'Lancer la partie');

  const form = el('form', {
    novalidate: true,
    onSubmit: async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const { match } = await post('/api/games', {
          mode: 'local',
          alias1: fields.alias1.input.value,
          alias2: fields.alias2.input.value,
          points_to_win: Number(points.select.value),
        });
        context.router.navigate(`/game/${match.id}`);
      } catch (error) {
        applyFormError(error, fields, banner);
        submit.disabled = false;
      }
    },
  },
    banner,
    fields.alias1,
    fields.alias2,
    points.node,
    submit,
    el('p', { class: 'form-text mt-3 mb-0' },
      'Gauche : touches W et S. Droite : fleches Haut et Bas.'),
  );

  return card('Partie a deux, meme clavier', form);
}


function tournamentForm(context) {
  const { user } = getState();
  const aliasList = el('div', { class: 'd-grid gap-2 mb-2' });
  const counter = el('p', { class: 'form-text mt-0' });
  const banner = el('div', { class: 'alert alert-danger d-none', role: 'alert' });

  const aliases = [];

  const refresh = () => {
    counter.textContent = `${aliases.length} joueur${aliases.length > 1 ? 's' : ''} `
      + `(de ${MIN_PLAYERS} a ${MAX_PLAYERS}).`;
    addButton.disabled = aliases.length >= MAX_PLAYERS;
    submit.disabled = aliases.length < MIN_PLAYERS;
  };

  const addAlias = (value = '') => {
    if (aliases.length >= MAX_PLAYERS) return;

    const input = el('input', {
      class: 'form-control',
      value,
      maxlength: 16,
      autocomplete: 'off',
      'aria-label': `Alias du joueur ${aliases.length + 1}`,
      placeholder: `Joueur ${aliases.length + 1}`,
    });
    const row = el('div', { class: 'input-group' },
      input,
      el('button', {
        class: 'btn btn-outline-secondary',
        type: 'button',
        'aria-label': 'Retirer ce joueur',
        onClick: () => {
          const index = aliases.indexOf(input);
          if (index >= 0) aliases.splice(index, 1);
          row.remove();
          refresh();
        },
      }, '×'),
    );

    aliases.push(input);
    aliasList.appendChild(row);
    refresh();
  };

  const addButton = el('button', {
    class: 'btn btn-outline-primary btn-sm',
    type: 'button',
    onClick: () => addAlias(),
  }, '+ Ajouter un joueur');

  const nameField = field('name', 'Nom du tournoi', {
    value: 'Tournoi', autocomplete: 'off', maxlength: 40,
  });
  const points = pointsSelect('points-tournament');
  const submit = el('button', { class: 'btn btn-primary w-100 mt-3', type: 'submit' },
    'Creer le tournoi');

  const form = el('form', {
    novalidate: true,
    onSubmit: async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const { tournament } = await post('/api/tournaments', {
          mode: 'local',
          name: nameField.input.value,
          points_to_win: Number(points.select.value),
          aliases: aliases.map((input) => input.value.trim()).filter(Boolean),
        });
        context.router.navigate(`/tournament/${tournament.id}`);
      } catch (error) {
        applyFormError(error, { name: nameField }, banner);
        submit.disabled = false;
      }
    },
  },
    banner,
    nameField,
    el('label', { class: 'form-label' }, 'Joueurs'),
    aliasList,
    counter,
    addButton,
    points.node,
    submit,
  );


  addAlias(user ? user.display_name : 'Joueur 1');
  for (let index = 2; index <= 4; index += 1) addAlias(`Joueur ${index}`);

  return card('Tournoi local', form);
}


function pointsSelect(id) {
  const select = el('select', { id, class: 'form-select' },
    [3, 5, 7, 11].map((value) => el('option', {
      value: String(value),
      selected: value === 5 ? true : null,
    }, `${value} points`)),
  );
  const node = el('div', { class: 'mb-3' },
    el('label', { class: 'form-label', for: id }, 'Score a atteindre'),
    select,
  );
  return { node, select };
}
