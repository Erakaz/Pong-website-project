import { el } from '../dom.js';

export default function render(context) {
  return el('div', { class: 'text-center py-5' },
    el('p', { class: 'display-1 fw-bold mb-2' }, '404'),
    el('h1', { class: 'h4 mb-3' }, 'Cette page n’existe pas'),
    el('p', { class: 'text-body-secondary' },
      'Aucune route ne correspond a ', el('code', {}, context.path), '.'),
    el('a', { class: 'btn btn-primary mt-3', href: '/' }, 'Retour a l’accueil'),
  );
}
