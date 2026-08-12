

import { startAttract } from '../attract.js';
import { el } from '../dom.js';
import { isAuthenticated } from '../store.js';

export default function render() {
  const canvas = el('canvas', {
    'aria-hidden': 'true',
  });

  const node = el('div', {},

    el('section', { class: 'hero' },
      el('p', { class: 'hero-tagline' }, '42 · depuis 1972'),
      el('h1', { class: 'hero-title' }, 'PONG'),
      el('p', { class: 'hero-lead' },
        'Deux raquettes, une balle, aucune excuse. Joue a deux sur le meme '
        + 'clavier, monte un tournoi, ou affronte quelqu’un a l’autre bout du '
        + 'reseau.'),

      el('div', { class: 'attract-screen' },
        canvas,
        el('p', { class: 'attract-caption' }, 'demonstration'),
      ),

      el('div', { class: 'd-flex flex-wrap justify-content-center gap-3' },
        el('a', { class: 'btn btn-primary btn-lg', href: '/play' }, 'Jouer'),
        isAuthenticated()
          ? el('a', { class: 'btn btn-outline-light btn-lg', href: '/online' },
            'En ligne')
          : el('a', { class: 'btn btn-outline-light btn-lg', href: '/register' },
            'Creer un compte'),
      ),
    ),


    el('section', { class: 'mt-4' },
      el('h2', { class: 'text-center mb-4' }, 'Commandes'),
      el('div', { class: 'controls-strip' },
        el('div', { class: 'text-center' },
          el('span', { class: 'control-key' }, 'W'),
          el('span', { class: 'control-key' }, 'S'),
          el('span', { class: 'control-label' }, 'Joueur de gauche'),
        ),
        el('div', { class: 'text-center' },
          el('span', { class: 'control-key' }, '↑'),
          el('span', { class: 'control-key' }, '↓'),
          el('span', { class: 'control-label' }, 'Joueur de droite'),
        ),
      ),
    ),
  );

  const stop = startAttract(canvas);


  return { node, cleanup: stop };
}
