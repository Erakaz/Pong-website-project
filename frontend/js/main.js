/**
 * Point d'entree de la SPA.
 *
 * Sequence de demarrage :
 *   1. interroger /api/health pour connaitre les modules actifs (OAuth 42) ;
 *   2. tenter de restaurer la session via le cookie de refresh httpOnly ;
 *   3. demarrer le routeur sur l'URL courante.
 *
 * Les etapes 1 et 2 peuvent echouer sans consequence (serveur qui demarre,
 * aucune session) : elles sont capturees, jamais laissees en rejet non gere,
 * car le sujet exige zero erreur en console.
 */

import { api, hasSessionCookie, refreshSession } from './api.js';
import { clear, el } from './dom.js';
import { bindToSession } from './live.js';
import { Router } from './router.js';
import { clearSession, getState, setFeatures, setReady, subscribe } from './store.js';
import { avatar, toast } from './ui.js';

/* -------------------------------------------------------------------------
 *  Definition des routes
 * ---------------------------------------------------------------------- */

const router = new Router(document.getElementById('app'));

router
  .register('/', () => import('./views/home.js'))
  .register('/play', () => import('./views/play.js'))
  .register('/online', () => import('./views/online.js'))
  .register('/game/:id', () => import('./views/game.js'))
  .register('/tournament/:id', () => import('./views/tournament.js'))
  .register('/login', () => import('./views/login.js'))
  .register('/login/2fa', () => import('./views/twofa.js'))
  .register('/register', () => import('./views/register.js'))
  .register('/profile', () => import('./views/profile.js'))
  .register('/users/:id', () => import('./views/profile.js'))
  .register('/friends', () => import('./views/friends.js'))
  .register('/chat', () => import('./views/chat.js'))
  .register('/chat/:id', () => import('./views/chat.js'))
  .register('/dashboard', () => import('./views/dashboard.js'))
  .register('/match/:id', () => import('./views/match.js'))
  .register('/settings', () => import('./views/settings.js'))
  .register('/privacy', () => import('./views/privacy.js'))
  .register('/diagnostic', () => import('./views/diagnostic.js'))
  .setNotFound(() => import('./views/notfound.js'));

/* -------------------------------------------------------------------------
 *  Barre de navigation
 * ---------------------------------------------------------------------- */

// `auth: true` = visible seulement connecte, `false` = seulement deconnecte,
// `null` = toujours visible.
const NAV_LINKS = [
  { href: '/', label: 'Accueil', auth: null },
  { href: '/play', label: 'Jouer', auth: null },
  { href: '/online', label: 'En ligne', auth: true },
  { href: '/friends', label: 'Amis', auth: true },
  { href: '/chat', label: 'Messages', auth: true },
  { href: '/dashboard', label: 'Stats', auth: true },
];

function renderNav(path) {
  const list = document.getElementById('nav-links');
  const session = document.getElementById('nav-session');
  if (!list || !session) return;

  const state = getState();
  const authenticated = Boolean(state.user);

  clear(list);
  for (const link of NAV_LINKS) {
    if (link.auth === true && !authenticated) continue;
    if (link.auth === false && authenticated) continue;

    const active = link.href === '/' ? path === '/' : path.startsWith(link.href);
    list.appendChild(
      el('li', { class: 'nav-item' },
        el('a', {
          class: `nav-link${active ? ' active' : ''}`,
          href: link.href,
          'aria-current': active ? 'page' : null,
        }, link.label),
      ),
    );
  }

  clear(session);
  session.appendChild(authenticated ? sessionMenu(state.user) : guestLinks());
}

function guestLinks() {
  return el('div', { class: 'd-flex gap-2' },
    el('a', { class: 'btn btn-sm btn-outline-light', href: '/login' }, 'Connexion'),
    el('a', { class: 'btn btn-sm btn-primary', href: '/register' }, 'Creer un compte'),
  );
}

function sessionMenu(user) {
  return el('div', { class: 'dropdown' },
    el('button', {
      class: 'btn btn-sm btn-outline-light dropdown-toggle d-flex align-items-center gap-2',
      type: 'button',
      'data-bs-toggle': 'dropdown',
      'aria-expanded': 'false',
    },
      avatar(user, 24),
      el('span', { class: 'text-truncate d-inline-block', style: { 'max-width': '10rem' } },
        user.display_name),
    ),
    el('ul', { class: 'dropdown-menu dropdown-menu-end' },
      el('li', {}, el('a', { class: 'dropdown-item', href: '/profile' }, 'Mon profil')),
      el('li', {}, el('a', { class: 'dropdown-item', href: '/friends' }, 'Mes amis')),
      el('li', {}, el('a', { class: 'dropdown-item', href: '/settings' }, 'Mon compte')),
      el('li', {}, el('hr', { class: 'dropdown-divider' })),
      el('li', {}, el('button', {
        class: 'dropdown-item',
        type: 'button',
        onClick: doLogout,
      }, 'Se deconnecter')),
    ),
  );
}

async function doLogout() {
  try {
    await api('/api/auth/logout', { method: 'POST', csrf: true, auth: false });
  } catch {
    // Meme si le serveur ne repond pas, la session locale doit disparaitre :
    // rester affiche comme connecte serait pire que tout.
  }
  clearSession();
  toast('Tu es deconnecte.', 'secondary');
  router.navigate('/');
}

router.onNavigate = renderNav;
subscribe(() => renderNav(window.location.pathname));

/* -------------------------------------------------------------------------
 *  Etat du serveur, affiche en pied de page
 * ---------------------------------------------------------------------- */

async function probeServer() {
  const footer = document.getElementById('footer-status');
  try {
    const health = await api('/api/health', { auth: false });
    setFeatures(health.features || {});
    if (footer) {
      footer.textContent = 'Serveur connecte';
      footer.className = 'text-success';
    }
  } catch {
    if (footer) {
      footer.textContent = 'Serveur injoignable';
      footer.className = 'text-danger';
    }
  }
}

/** Restaure la session si le cookie de refresh est encore valide. */
async function restoreSession() {
  try {
    // Aucun temoin de session : inutile d'interroger le serveur, et cela
    // evite un 401 que Chrome afficherait en rouge dans la console.
    if (hasSessionCookie()) await refreshSession();
  } catch {
    // Session expiree ou revoquee : on repart simplement deconnecte.
  } finally {
    setReady(true);
  }
}

/* -------------------------------------------------------------------------
 *  Demarrage
 * ---------------------------------------------------------------------- */

async function boot() {
  // La socket de session s'ouvre et se ferme toute seule en suivant l'etat
  // d'authentification ; aucune vue n'a a s'en preoccuper.
  bindToSession();

  await Promise.all([probeServer(), restoreSession()]);
  await router.start();
}

// Un rejet non capture s'afficherait en rouge dans la console : on les
// intercepte pour les journaliser proprement, sans jamais masquer un vrai bug.
window.addEventListener('unhandledrejection', (event) => {
  console.error('Promesse rejetee sans gestionnaire :', event.reason);
});

boot().catch((error) => {
  console.error('Demarrage de l’application en echec', error);
});
