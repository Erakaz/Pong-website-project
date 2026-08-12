

import { clearSession, getState, setSession } from './store.js';

const CSRF_COOKIE = 'ftt_csrf';
const CSRF_HEADER = 'X-CSRF-Token';

export class ApiError extends Error {
  constructor(code, message, status, details = {}) {
    super(message || code);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function readCookie(name) {


  const prefix = `${name}=`;
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) return decodeURIComponent(trimmed.slice(prefix.length));
  }
  return null;
}


export function hasSessionCookie() {
  return readCookie(CSRF_COOKIE) !== null;
}

async function parseResponse(response) {
  if (response.status === 204) return null;
  const type = response.headers.get('Content-Type') || '';
  if (!type.includes('application/json')) {
    if (response.ok) return null;
    throw new ApiError('unexpected_response',
      `Reponse inattendue du serveur (${response.status}).`, response.status);
  }
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError('invalid_json', 'Reponse illisible du serveur.', response.status);
  }
  if (response.ok) return payload;

  const error = (payload && payload.error) || {};
  throw new ApiError(error.code || 'error',
    error.message || `Erreur ${response.status}.`, response.status, error.details || {});
}


let refreshInFlight = null;

export function refreshSession() {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const headers = { Accept: 'application/json' };
      const csrf = readCookie(CSRF_COOKIE);
      if (csrf) headers[CSRF_HEADER] = csrf;

      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers,
        credentials: 'same-origin',
      });
      const data = await parseResponse(response);
      setSession({
        accessToken: data.access_token,
        expiresIn: data.expires_in,
        user: data.user,
      });
      return data;
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}


export async function api(path, options = {}) {
  const {
    method = 'GET',
    body,
    formData,
    auth = true,
    csrf = false,
    signal,
    retryOnExpired = true,
  } = options;

  const headers = { Accept: 'application/json' };
  const state = getState();

  if (auth && state.accessToken) {
    headers.Authorization = `Bearer ${state.accessToken}`;
  }
  if (csrf) {
    const token = readCookie(CSRF_COOKIE);
    if (token) headers[CSRF_HEADER] = token;
  }

  let payload;
  if (formData) {
    payload = formData;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: payload,
      credentials: 'same-origin',
      signal,
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError('network_error',
      'Serveur injoignable. Verifie ta connexion.', 0);
  }

  try {
    return await parseResponse(response);
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;


    if (error.code === 'token_expired' && auth && retryOnExpired) {
      try {
        await refreshSession();
      } catch {
        clearSession();
        throw error;
      }
      return api(path, { ...options, retryOnExpired: false });
    }

    if (error.status === 401 && auth) clearSession();
    throw error;
  }
}

export const get = (path, options) => api(path, { ...options, method: 'GET' });
export const post = (path, body, options) => api(path, { ...options, method: 'POST', body });
export const patch = (path, body, options) => api(path, { ...options, method: 'PATCH', body });
export const del = (path, options) => api(path, { ...options, method: 'DELETE' });
