

import { el, frag } from './dom.js';


export function pageHeader(title, { subtitle = null, actions = null } = {}) {
  return el('div', { class: 'd-flex flex-wrap justify-content-between align-items-start gap-3 mb-4' },
    el('div', {},
      el('h1', { class: 'h3 mb-1' }, title),
      subtitle ? el('p', { class: 'text-body-secondary mb-0' }, subtitle) : null,
    ),
    actions ? el('div', { class: 'd-flex gap-2 flex-wrap' }, actions) : null,
  );
}

export function card(title, ...children) {
  return el('div', { class: 'card h-100' },
    el('div', { class: 'card-body' },
      title ? el('h2', { class: 'card-title h5' }, title) : null,
      ...children,
    ),
  );
}

export function spinner(label = 'Chargement…') {
  return el('div', { class: 'd-flex align-items-center gap-2 text-body-secondary py-4' },
    el('span', { class: 'spinner-border spinner-border-sm', 'aria-hidden': 'true' }),
    el('span', { role: 'status' }, label),
  );
}

export function alert(message, variant = 'danger') {
  return el('div', { class: `alert alert-${variant}`, role: 'alert' }, message);
}


export function fieldError(id, message) {
  return el('div', { id, class: 'invalid-feedback d-block' }, message);
}


export function toast(message, variant = 'primary', { timeout = 5000 } = {}) {
  const container = document.getElementById('toasts');
  if (!container) return;

  const node = el('div', {
    class: `toast align-items-center text-bg-${variant} border-0 show`,
    role: 'alert',
  },
    el('div', { class: 'd-flex' },
      el('div', { class: 'toast-body' }, message),
      el('button', {
        type: 'button',
        class: 'btn-close btn-close-white me-2 m-auto',
        'aria-label': 'Fermer',
        onClick: () => node.remove(),
      }),
    ),
  );

  container.appendChild(node);
  if (timeout > 0) window.setTimeout(() => node.remove(), timeout);
  return node;
}


export function field(name, label, { type = 'text', value = '', autocomplete = null,
  required = true, help = null, ...rest } = {}) {
  const inputId = `field-${name}`;
  const errorId = `${inputId}-error`;
  const helpId = `${inputId}-help`;

  const input = el('input', {
    id: inputId,
    name,
    type,
    class: 'form-control',
    value,
    autocomplete,
    required,
    'aria-describedby': [help ? helpId : null, errorId].filter(Boolean).join(' '),
    ...rest,
  });

  const error = el('div', { id: errorId, class: 'invalid-feedback' });

  const wrapper = el('div', { class: 'mb-3' },
    el('label', { class: 'form-label', for: inputId }, label),
    input,
    help ? el('div', { id: helpId, class: 'form-text' }, help) : null,
    error,
  );

  wrapper.input = input;
  wrapper.showError = (message) => {
    input.classList.add('is-invalid');
    error.textContent = message;
  };
  wrapper.clearError = () => {
    input.classList.remove('is-invalid');
    error.textContent = '';
  };
  return wrapper;
}


export function applyFormError(error, fields, banner) {
  for (const wrapper of Object.values(fields)) wrapper.clearError();

  const target = error.details && error.details.field;
  if (target && fields[target]) {
    fields[target].showError(error.message);
    fields[target].input.focus();
    banner.textContent = '';
    banner.classList.add('d-none');
    return;
  }
  banner.textContent = error.message;
  banner.classList.remove('d-none');
}

export function emptyState(message, ...children) {
  return el('div', { class: 'text-center text-body-secondary py-5' },
    el('p', { class: 'mb-3' }, message),
    ...children,
  );
}

export function avatar(user, size = 40) {
  return el('img', {
    src: user.avatar_url,
    alt: `Avatar de ${user.display_name}`,
    width: size,
    height: size,
    class: 'rounded-circle object-fit-cover flex-shrink-0',
    loading: 'lazy',
  });
}

export { frag };
