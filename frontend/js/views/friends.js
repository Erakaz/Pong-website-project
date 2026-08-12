

import { del, get, post } from '../api.js';
import { clear, el } from '../dom.js';
import { isOnline, on, seed } from '../live.js';
import { alert as alertBox, avatar, card, emptyState, pageHeader, toast } from '../ui.js';

export default async function render() {
  let data;
  try {
    data = await get('/api/friends');
  } catch (error) {
    return el('div', {}, alertBox(`Liste indisponible : ${error.message}`));
  }

  const friendsList = el('div', { class: 'd-grid gap-2' });
  const incomingList = el('div', { class: 'd-grid gap-2' });
  const outgoingList = el('div', { class: 'd-grid gap-2' });

  const seedFromResponse = () => {
    seed([...data.friends, ...data.incoming, ...data.outgoing]
      .filter((entry) => entry.user.online)
      .map((entry) => entry.user.id));
  };
  seedFromResponse();

  const refresh = async () => {
    try {
      data = await get('/api/friends');
    } catch {
      return;
    }
    seedFromResponse();
    paint();
  };

  const paint = () => {
    clear(friendsList);
    clear(incomingList);
    clear(outgoingList);

    if (data.friends.length === 0) {
      friendsList.appendChild(emptyState('Aucun ami pour l’instant.'));
    }
    for (const entry of data.friends) {
      friendsList.appendChild(friendRow(entry, [
        actionButton('Retirer', 'btn-outline-secondary',
          () => del(`/api/friends/${entry.id}`).then(refresh)),
      ]));
    }

    for (const entry of data.incoming) {
      incomingList.appendChild(friendRow(entry, [
        actionButton('Accepter', 'btn-primary',
          () => post(`/api/friends/${entry.id}/accept`, {}).then(refresh)),
        actionButton('Refuser', 'btn-outline-secondary',
          () => del(`/api/friends/${entry.id}`).then(refresh)),
      ]));
    }
    if (data.incoming.length === 0) {
      incomingList.appendChild(el('p', { class: 'form-text mb-0' }, 'Aucune demande recue.'));
    }

    for (const entry of data.outgoing) {
      outgoingList.appendChild(friendRow(entry, [
        actionButton('Annuler', 'btn-outline-secondary',
          () => del(`/api/friends/${entry.id}`).then(refresh)),
      ]));
    }
    if (data.outgoing.length === 0) {
      outgoingList.appendChild(el('p', { class: 'form-text mb-0' }, 'Aucune demande envoyee.'));
    }
  };

  paint();


  const unsubscribe = on('presence', paint);

  const node = el('div', {},
    pageHeader('Amis', { subtitle: 'Ajoute des joueurs et vois qui est connecte.' }),
    el('div', { class: 'row g-4' },
      el('div', { class: 'col-12 col-lg-7' },
        card('Mes amis', friendsList),
        el('div', { class: 'mt-4' }, card('Demandes recues', incomingList)),
        el('div', { class: 'mt-4' }, card('Demandes envoyees', outgoingList)),
      ),
      el('div', { class: 'col-12 col-lg-5' }, searchCard(refresh)),
    ),
  );

  return { node, cleanup: unsubscribe };
}

function friendRow(entry, actions) {
  const user = entry.user;


  const online = isOnline(user.id);

  return el('div', {
    class: 'd-flex align-items-center gap-3 border border-secondary-subtle rounded p-2',
  },
    avatar(user, 40),
    el('div', { class: 'flex-grow-1 min-width-0' },
      el('a', { href: `/users/${user.id}`, class: 'd-block text-truncate' }, user.display_name),
      el('span', { class: `badge text-bg-${online ? 'success' : 'secondary'}` },
        online ? 'en ligne' : lastSeenLabel(user.last_seen)),
    ),
    el('div', { class: 'd-flex gap-2' }, actions),
  );
}

function lastSeenLabel(iso) {
  if (!iso) return 'hors ligne';
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 60) return `vu il y a ${Math.max(1, minutes)} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `vu il y a ${hours} h`;
  return `vu il y a ${Math.round(hours / 24)} j`;
}

function actionButton(label, variant, action) {
  return el('button', {
    class: `btn btn-sm ${variant}`,
    type: 'button',
    onClick: async (event) => {
      event.currentTarget.disabled = true;
      try {
        await action();
      } catch (error) {
        toast(error.message, 'danger');
        event.currentTarget.disabled = false;
      }
    },
  }, label);
}


function searchCard(refresh) {
  const results = el('div', { class: 'd-grid gap-2 mt-3' });
  const input = el('input', {
    class: 'form-control',
    type: 'search',
    id: 'friend-search',
    placeholder: 'Pseudo…',
    autocomplete: 'off',
  });

  let timer = null;
  const search = async () => {
    const query = input.value.trim();
    clear(results);
    if (query.length < 2) return;

    try {
      const data = await get(`/api/users?q=${encodeURIComponent(query)}`);
      if (data.users.length === 0) {
        results.appendChild(el('p', { class: 'form-text mb-0' }, 'Aucun joueur trouve.'));
        return;
      }
      seed(data.users.filter((user) => user.online).map((user) => user.id));
      for (const user of data.users) {
        results.appendChild(el('div', {
          class: 'd-flex align-items-center gap-2 border border-secondary-subtle rounded p-2',
        },
          avatar(user, 32),
          el('a', { href: `/users/${user.id}`, class: 'flex-grow-1 text-truncate' },
            user.display_name),
          actionButton('Ajouter', 'btn-primary', async () => {
            await post('/api/friends', { display_name: user.display_name });
            toast('Demande envoyee.', 'success');
            await refresh();
          }),
        ));
      }
    } catch (error) {
      results.appendChild(alertBox(error.message));
    }
  };


  input.addEventListener('input', () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(search, 250);
  });

  return card('Chercher un joueur',
    el('label', { class: 'form-label visually-hidden', for: 'friend-search' }, 'Pseudo'),
    input,
    results,
  );
}
