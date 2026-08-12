/**
 * Etat de session, en memoire uniquement.
 *
 * Choix de securite : l'access token n'est JAMAIS ecrit dans localStorage ni
 * sessionStorage. Ces deux stockages sont lisibles par n'importe quel script
 * de la page, donc par une XSS. Ici le jeton vit dans une variable de module :
 * il disparait au rechargement de l'onglet, et c'est le refresh token — dans
 * un cookie httpOnly, hors de portee du JavaScript — qui permet de retrouver
 * une session au demarrage.
 */

const listeners = new Set();

const state = {
  accessToken: null,
  accessExpiresAt: 0,   // horodatage local (ms) d'expiration estimee
  user: null,           // objet utilisateur prive, ou null si deconnecte
  features: {},         // drapeaux renvoyes par /api/health (ex. oauth42)
  ready: false,         // true une fois la session initiale resolue
};

export function getState() {
  return state;
}

export function isAuthenticated() {
  return Boolean(state.user);
}

export function setSession({ accessToken, expiresIn, user }) {
  state.accessToken = accessToken || null;
  state.accessExpiresAt = accessToken ? Date.now() + (expiresIn || 0) * 1000 : 0;
  if (user !== undefined) state.user = user;
  notify();
}

export function setUser(user) {
  state.user = user;
  notify();
}

export function clearSession() {
  state.accessToken = null;
  state.accessExpiresAt = 0;
  state.user = null;
  notify();
}

export function setFeatures(features) {
  state.features = features || {};
  notify();
}

export function setReady(value) {
  state.ready = Boolean(value);
  notify();
}

/** S'abonner aux changements de session (navbar, vues, socket de presence). */
export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify() {
  for (const listener of listeners) {
    try {
      listener(state);
    } catch (error) {
      console.error('Abonne a l’etat en echec', error);
    }
  }
}
