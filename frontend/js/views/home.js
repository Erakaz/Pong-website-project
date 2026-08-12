import { el } from '../dom.js';
import { getState } from '../store.js';
import { card, pageHeader } from '../ui.js';

/** Etat d'avancement du projet, affiche sur l'accueil pendant le developpement. */
const MODULES = [
  { weight: 'Majeur', label: 'Django en backend' },
  { weight: 'Majeur', label: 'Comptes, profils, amis, historique' },
  { weight: 'Majeur', label: 'Connexion 42 (OAuth 2.0)' },
  { weight: 'Majeur', label: 'Parties entre joueurs distants' },
  { weight: 'Majeur', label: 'Messagerie directe et invitations' },
  { weight: 'Majeur', label: 'Double authentification et JWT' },
  { weight: 'Majeur', label: 'Pong cote serveur et API' },
  { weight: 'Mineur', label: 'Toolkit Bootstrap' },
  { weight: 'Mineur', label: 'Base PostgreSQL' },
  { weight: 'Mineur', label: 'Tableaux de bord statistiques' },
  { weight: 'Mineur', label: 'Conformite RGPD' },
];

export default function render() {
  const { features } = getState();

  const node = el('div', {},
    pageHeader('Pong', {
      subtitle: 'Le tournoi de Pong de 42. Affronte un adversaire au clavier, '
        + 'ou en ligne quand le module sera en place.',
      actions: [
        el('a', { class: 'btn btn-primary', href: '/play' }, 'Jouer maintenant'),
        el('a', { class: 'btn btn-outline-secondary', href: '/diagnostic' },
          'Verifier la connexion'),
      ],
    }),

    el('div', { class: 'row g-4' },
      el('div', { class: 'col-12 col-lg-7' },
        card('Modules realises',
          el('p', { class: 'form-text mt-0' },
            '7 modules majeurs et 4 mineurs, soit 9 majeurs equivalents '
            + '(7 requis pour 100 %).'),
          el('ul', { class: 'list-unstyled mb-0' },
            MODULES.map((module) => el('li', {
              class: 'd-flex gap-2 align-items-center mb-2',
            },
              el('span', {
                class: `badge text-bg-${module.weight === 'Majeur' ? 'primary' : 'secondary'}`,
              }, module.weight),
              el('span', {}, module.label),
            )),
          ),
        ),
      ),

      el('div', { class: 'col-12 col-lg-5' },
        card('Modules actifs',
          el('dl', { class: 'row mb-0' },
            el('dt', { class: 'col-7' }, 'Connexion 42 (OAuth)'),
            el('dd', { class: 'col-5 text-end' },
              el('span', {
                class: `badge text-bg-${features.oauth42 ? 'success' : 'secondary'}`,
              }, features.oauth42 ? 'configuree' : 'non configuree'),
            ),
          ),
          el('p', { class: 'form-text mb-0 mt-3' },
            'La connexion 42 s’active en renseignant OAUTH42_UID et '
            + 'OAUTH42_SECRET dans le fichier .env.'),
        ),
      ),
    ),
  );

  return node;
}
