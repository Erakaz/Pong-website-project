

import { get, post } from '../api.js';
import { clear, el } from '../dom.js';
import { isOnline, on } from '../live.js';
import { getState } from '../store.js';
import { alert as alertBox, avatar, emptyState, pageHeader, toast } from '../ui.js';

export default async function render(context) {
  const { user: me } = getState();
  if (!me) {
    context.router.navigate('/login?next=/chat', { replace: true });
    return el('div', {});
  }

  const selectedId = context.params.id ? Number(context.params.id) : null;

  let index;
  try {
    index = await get('/api/chat/conversations');
  } catch (error) {
    return el('div', {}, alertBox(error.message));
  }

  const listColumn = el('div', { class: 'list-group' });
  const threadColumn = el('div', { class: 'card h-100' });

  const paintList = () => {
    clear(listColumn);
    if (index.conversations.length === 0) {
      listColumn.appendChild(emptyState('Aucune conversation.',
        el('a', { class: 'btn btn-sm btn-primary', href: '/friends' }, 'Trouver des joueurs')));
      return;
    }
    for (const entry of index.conversations) {
      const active = entry.user.id === selectedId;
      listColumn.appendChild(el('a', {
        class: `list-group-item list-group-item-action d-flex align-items-center gap-2${active ? ' active' : ''}`,
        href: `/chat/${entry.user.id}`,
      },
        avatar(entry.user, 32),
        el('span', { class: 'flex-grow-1 text-truncate' }, entry.user.display_name),
        isOnline(entry.user.id) ? el('span', { class: 'badge text-bg-success' }, '•') : null,
        entry.unread ? el('span', { class: 'badge text-bg-primary' }, 'nouveau') : null,
      ));
    }
  };
  paintList();

  const thread = selectedId
    ? await buildThread(selectedId, me, context)
    : { node: emptyState('Choisis une conversation a gauche.'), cleanup: null };

  threadColumn.appendChild(thread.node);


  const unsubscribe = on('chat', async () => {
    try {
      index = await get('/api/chat/conversations');
      paintList();
    } catch {

    }
  });

  const node = el('div', {},
    pageHeader('Messages', { subtitle: 'Discute, invite a jouer, ou bloque un joueur.' }),
    el('div', { class: 'row g-4' },
      el('div', { class: 'col-12 col-md-4' }, listColumn),
      el('div', { class: 'col-12 col-md-8' }, threadColumn),
    ),
  );

  return {
    node,
    cleanup() {
      unsubscribe();
      if (thread.cleanup) thread.cleanup();
    },
  };
}


async function buildThread(otherId, me, context) {
  let data;
  try {
    data = await get(`/api/chat/with/${otherId}`);
  } catch (error) {
    return { node: alertBox(error.message), cleanup: null };
  }

  const other = data.user;
  const messages = el('div', {
    class: 'd-flex flex-column gap-2 p-3 overflow-auto',
    style: { 'max-height': '26rem', 'min-height': '18rem' },
  });

  const append = (message) => {

    const involved = [message.sender_id, message.recipient_id];
    if (!involved.includes(otherId) && message.kind !== 'system') return;
    messages.appendChild(bubble(message, me, other));
    messages.scrollTop = messages.scrollHeight;
  };

  for (const message of data.messages) append(message);
  if (data.messages.length === 0) {
    messages.appendChild(el('p', { class: 'text-body-secondary text-center my-auto' },
      'Aucun message. Lance la conversation !'));
  }

  const input = el('input', {
    class: 'form-control',
    id: 'chat-input',
    placeholder: 'Ecrire un message…',
    autocomplete: 'off',
    maxlength: 1000,
    disabled: data.blocked || null,
  });

  const form = el('form', {
    class: 'input-group p-3 border-top border-secondary-subtle',
    onSubmit: async (event) => {
      event.preventDefault();
      const body = input.value.trim();
      if (!body) return;
      input.value = '';
      try {
        await post(`/api/chat/with/${otherId}`, { body });
      } catch (error) {
        toast(error.message, 'danger');
      }
    },
  },
    el('label', { class: 'visually-hidden', for: 'chat-input' }, 'Message'),
    input,
    el('button', { class: 'btn btn-primary', type: 'submit', disabled: data.blocked || null },
      'Envoyer'),
  );

  const blockButton = el('button', {
    class: `btn btn-sm ${data.blocked ? 'btn-outline-success' : 'btn-outline-danger'}`,
    type: 'button',
    onClick: async (event) => {
      event.currentTarget.disabled = true;
      try {
        await post(`/api/chat/with/${otherId}/block`, { blocked: !data.blocked });
        context.router.navigate(`/chat/${otherId}`);
      } catch (error) {
        toast(error.message, 'danger');
        event.currentTarget.disabled = false;
      }
    },
  }, data.blocked ? 'Debloquer' : 'Bloquer');

  const header = el('div', {
    class: 'card-header d-flex align-items-center gap-2 flex-wrap',
  },
    avatar(other, 32),

    el('a', { class: 'flex-grow-1 text-truncate', href: `/users/${other.id}` },
      other.display_name),
    el('button', {
      class: 'btn btn-sm btn-primary',
      type: 'button',
      disabled: data.blocked || null,
      onClick: async (event) => {
        event.currentTarget.disabled = true;
        try {
          const result = await post(`/api/chat/with/${otherId}/invite`, {});
          toast('Invitation envoyee.', 'success');
          context.router.navigate(`/game/${result.match.id}`);
        } catch (error) {
          toast(error.message, 'danger');
          event.currentTarget.disabled = false;
        }
      },
    }, 'Inviter a jouer'),
    blockButton,
  );

  const unsubscribe = on('chat', (payload) => append(payload.message));

  const node = el('div', { class: 'd-flex flex-column h-100' },
    header,
    data.blocked
      ? el('div', { class: 'alert alert-secondary m-3 mb-0' },
        'Tu as bloque ce joueur : vous ne pouvez plus vous ecrire.')
      : null,
    messages,
    form,
  );

  return { node, cleanup: unsubscribe };
}

function bubble(message, me, other) {
  if (message.kind === 'system') {
    return el('div', { class: 'alert alert-info py-2 px-3 mb-0 small' },
      message.body,
      message.match_id
        ? el('a', { class: 'btn btn-sm btn-primary ms-2', href: `/game/${message.match_id}` },
          'Jouer')
        : null,
    );
  }

  const mine = message.sender_id === me.id;
  const when = new Date(message.created_at).toLocaleTimeString('fr-FR',
    { hour: '2-digit', minute: '2-digit' });

  return el('div', { class: `d-flex ${mine ? 'justify-content-end' : ''}` },
    el('div', {
      class: `rounded px-3 py-2 ${mine ? 'text-bg-primary' : 'border border-secondary-subtle'}`,
      style: { 'max-width': '80%' },
    },
      el('div', {}, message.body),
      message.kind === 'invite' && message.match_id
        ? el('a', {
          class: `btn btn-sm mt-2 ${mine ? 'btn-light' : 'btn-primary'}`,
          href: `/game/${message.match_id}`,
        }, 'Rejoindre la partie')
        : null,
      el('div', { class: 'small opacity-75 mt-1' }, when),
    ),
  );
}
