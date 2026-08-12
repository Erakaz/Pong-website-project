

import { api } from '../api.js';
import { el } from '../dom.js';
import { card, pageHeader } from '../ui.js';

function row(label, valueNode) {
  return el('div', { class: 'd-flex justify-content-between gap-3 py-2 border-bottom border-secondary-subtle' },
    el('span', { class: 'text-body-secondary' }, label),
    valueNode,
  );
}

function badge(state, textValue) {
  const variant = { ok: 'success', pending: 'secondary', fail: 'danger' }[state] || 'secondary';
  return el('span', { class: `badge text-bg-${variant}` }, textValue);
}

export default function render() {
  const httpValue = el('span', {}, badge('pending', 'test en cours…'));
  const wsValue = el('span', {}, badge('pending', 'test en cours…'));
  const tlsValue = el('span', {},
    badge(window.location.protocol === 'https:' ? 'ok' : 'fail',
      window.location.protocol === 'https:' ? 'HTTPS actif' : 'HTTP non chiffre'));

  let socket = null;
  let cancelled = false;

  const replace = (holder, node) => {
    if (cancelled) return;
    holder.replaceChildren(node);
  };


  (async () => {
    const start = performance.now();
    try {
      const health = await api('/api/health', { auth: false });
      const ms = Math.round(performance.now() - start);
      replace(httpValue, badge('ok', `${health.status} — ${ms} ms`));
    } catch (error) {
      replace(httpValue, badge('fail', error.message));
    }
  })();


  try {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    socket = new WebSocket(`${scheme}://${window.location.host}/ws/ping`);
    let sentAt = 0;

    socket.addEventListener('open', () => {
      sentAt = performance.now();
      socket.send(JSON.stringify({ type: 'ping' }));
    });
    socket.addEventListener('message', (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (payload.type === 'pong') {
        const ms = Math.round(performance.now() - sentAt);
        replace(wsValue, badge('ok', `aller-retour ${ms} ms`));
        socket.close(1000, 'diagnostic termine');
      }
    });
    socket.addEventListener('error', () => {
      replace(wsValue, badge('fail', 'connexion impossible'));
    });
    socket.addEventListener('close', (event) => {

      if (!cancelled && event.code !== 1000) {
        replace(wsValue, badge('fail', `fermeture ${event.code}`));
      }
    });
  } catch (error) {
    replace(wsValue, badge('fail', String(error.message || error)));
  }

  const node = el('div', {},
    pageHeader('Diagnostic', {
      subtitle: 'Verification des canaux HTTPS et WSS entre le navigateur, '
        + 'nginx et le serveur applicatif.',
    }),
    el('div', { class: 'row' },
      el('div', { class: 'col-12 col-lg-8' },
        card(null,
          row('Transport de la page', tlsValue),
          row('API — GET /api/health', httpValue),
          row('WebSocket — wss:///ws/ping', wsValue),
          el('p', { class: 'form-text mt-3 mb-0' },
            'Le certificat est auto-signe : l’avertissement du navigateur au '
            + 'premier acces est attendu et sans rapport avec ces tests.'),
        ),
      ),
    ),
  );

  return {
    node,


    cleanup() {
      cancelled = true;
      if (socket && socket.readyState <= WebSocket.OPEN) {
        socket.close(1000, 'navigation');
      }
    },
  };
}
