

const listeners = new Set();

const state = {
  accessToken: null,
  accessExpiresAt: 0,
  user: null,
  features: {},
  ready: false,
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
