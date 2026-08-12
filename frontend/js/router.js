/**
 * Routeur SPA base sur l'History API.
 *
 * Le sujet exige que les boutons Precedent et Suivant du navigateur
 * fonctionnent : c'est `pushState` + l'evenement `popstate` qui le
 * garantissent, et nginx renvoie index.html pour toute URL inconnue afin
 * qu'un rechargement direct sur /profile fonctionne aussi.
 *
 * Chaque vue peut retourner une fonction de nettoyage. Le routeur l'appelle
 * AVANT d'afficher la vue suivante : c'est ce qui ferme les WebSockets et
 * arrete les boucles d'animation du jeu, sinon quitter une partie laisserait
 * une socket ouverte et une requestAnimationFrame tournant en fond.
 */

import { clear, el } from './dom.js';

/** Transforme "/users/:name" en expression reguliere + liste de parametres. */
function compile(pattern) {
  const params = [];
  const source = pattern
    .replace(/[.+*?^${}()|[\]\\]/g, '\\$&')
    .replace(/\/:([A-Za-z0-9_]+)/g, (_, name) => {
      params.push(name);
      return '/([^/]+)';
    });
  return { regex: new RegExp(`^${source}/?$`), params };
}

export class Router {
  /**
   * @param {HTMLElement} outlet noeud dans lequel les vues sont montees
   */
  constructor(outlet) {
    this.outlet = outlet;
    this.routes = [];
    this.notFound = null;
    this.current = null;      // { cleanup, path }
    this.renderToken = 0;     // annule le rendu d'une vue devenue obsolete
    this.onNavigate = null;   // rappel utilise pour surligner le menu actif
  }

  /**
   * @param {string} pattern  "/", "/game/:id"
   * @param {() => Promise<{default: (ctx) => (Node|Promise<Node>)}>} loader
   *        import dynamique du module de vue
   */
  register(pattern, loader) {
    this.routes.push({ ...compile(pattern), pattern, loader });
    return this;
  }

  setNotFound(loader) {
    this.notFound = loader;
    return this;
  }

  match(path) {
    for (const route of this.routes) {
      const found = route.regex.exec(path);
      if (!found) continue;
      const params = {};
      route.params.forEach((name, index) => {
        params[name] = decodeURIComponent(found[index + 1]);
      });
      return { route, params };
    }
    return null;
  }

  start() {
    // Interception globale des liens internes : un seul gestionnaire pour
    // toute l'application, y compris les liens crees dynamiquement.
    document.addEventListener('click', (event) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

      const anchor = event.target.closest('a');
      if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return;

      const href = anchor.getAttribute('href');
      if (!href || href.startsWith('#')) return;

      const url = new URL(href, window.location.origin);
      if (url.origin !== window.location.origin) return;   // lien externe
      if (url.pathname.startsWith('/media/')) return;      // fichier servi par nginx

      event.preventDefault();
      this.navigate(url.pathname + url.search);
    });

    window.addEventListener('popstate', () => {
      this.render(window.location.pathname + window.location.search);
    });

    return this.render(window.location.pathname + window.location.search);
  }

  navigate(path, { replace = false } = {}) {
    const current = window.location.pathname + window.location.search;
    if (path === current) return this.render(path);
    if (replace) window.history.replaceState({}, '', path);
    else window.history.pushState({}, '', path);
    return this.render(path);
  }

  async render(fullPath) {
    const token = ++this.renderToken;
    const [path, search = ''] = fullPath.split('?');

    // Nettoyage de la vue precedente avant tout : une vue de jeu doit fermer
    // sa socket meme si le chargement de la suivante echoue.
    if (this.current && typeof this.current.cleanup === 'function') {
      try {
        this.current.cleanup();
      } catch (error) {
        console.error('Nettoyage de vue en echec', error);
      }
    }
    this.current = null;

    const matched = this.match(path);
    const loader = matched ? matched.route.loader : this.notFound;
    if (!loader) return;

    const context = {
      path,
      params: matched ? matched.params : {},
      query: new URLSearchParams(search),
      router: this,
    };

    let view;
    try {
      const module = await loader();
      if (token !== this.renderToken) return;  // une autre navigation a pris le relais
      view = await module.default(context);
    } catch (error) {
      if (token !== this.renderToken) return;
      console.error('Chargement de vue en echec', error);
      view = { node: renderCrash(error) };
    }
    if (token !== this.renderToken) return;

    // Une vue retourne soit un noeud, soit { node, cleanup }.
    const node = view instanceof Node ? view : view.node;
    const cleanup = view instanceof Node ? null : view.cleanup;

    clear(this.outlet);
    this.outlet.appendChild(node);
    this.current = { cleanup, path };

    if (typeof this.onNavigate === 'function') this.onNavigate(path);

    // Une SPA ne repositionne pas le defilement toute seule, et le focus
    // resterait sur le lien clique : les deux sont retablis a la main pour
    // que la navigation au clavier et au lecteur d'ecran reste coherente.
    window.scrollTo(0, 0);
    this.outlet.focus({ preventScroll: true });
  }
}

function renderCrash(error) {
  return el('div', { class: 'alert alert-danger', role: 'alert' },
    el('h2', { class: 'h5' }, 'Cette page n’a pas pu s’afficher'),
    el('p', { class: 'mb-0' }, String(error && error.message ? error.message : error)),
  );
}
