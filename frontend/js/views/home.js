/**
 * Page d'accueil.
 *
 * Une borne d'arcade : le titre, l'ecran d'attente qui joue tout seul, et
 * l'invitation a lancer une partie. Rien d'autre — l'etat d'avancement du
 * projet n'a pas sa place ici, il est dans docs/.
 */

import { startAttract } from '../attract.js';
import { el } from '../dom.js';
import { isAuthenticated } from '../store.js';

const FEATURES = [
  {
    index: '01',
    title: 'Tournois',
    text: 'Elimination directe, de 2 a 16 joueurs. Le tableau affiche qui '
      + 'affronte qui, dans quel ordre, et annonce la rencontre suivante.',
  },
  {
    index: '02',
    title: 'En ligne',
    text: 'Affronte quelqu’un sur une autre machine. La partie est simulee par '
      + 'le serveur : personne ne peut tricher, et une coupure reseau ne fait '
      + 'pas perdre le match.',
  },
  {
    index: '03',
    title: 'Statistiques',
    text: 'Victoires, series, points marques, plus long echange. Chaque partie '
      + 'garde le detail de son deroule, point par point.',
  },
];

export default function render() {
  const canvas = el('canvas', {
    'aria-hidden': 'true',      // decoratif : rien a annoncer a un lecteur d'ecran
  });

  const node = el('div', {},
    /* --- Banniere ------------------------------------------------------- */
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

    /* --- Ce que le site propose ----------------------------------------- */
    el('section', { class: 'row g-4 mt-1' },
      FEATURES.map((feature) => el('div', { class: 'col-12 col-md-4' },
        el('article', { class: 'feature' },
          el('span', { class: 'feature-index' }, feature.index),
          el('h2', {}, feature.title),
          el('p', {}, feature.text),
        ),
      )),
    ),

    /* --- Commandes ------------------------------------------------------- */
    el('section', { class: 'mt-5' },
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

  // Contrat du routeur : quitter la page arrete la boucle d'animation.
  return { node, cleanup: stop };
}
