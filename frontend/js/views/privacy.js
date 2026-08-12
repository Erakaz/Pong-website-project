

import { api, get, post } from '../api.js';
import { el } from '../dom.js';
import { clearSession, getState } from '../store.js';
import { alert as alertBox, card, field, pageHeader, toast } from '../ui.js';

export default async function render(context) {
  let summary;
  try {
    summary = await get('/api/privacy', { auth: false });
  } catch (error) {
    return el('div', {}, alertBox(error.message));
  }

  const { user } = getState();

  return el('div', {},
    pageHeader('Donnees et vie privee', {
      subtitle: 'Ce que ce site conserve, pourquoi, et comment reprendre la main.',
    }),

    el('div', { class: 'row g-4' },
      el('div', { class: 'col-12 col-lg-7' },
        card('Donnees conservees',
          el('dl', { class: 'mb-0' },
            summary.collected.map((item) => [
              el('dt', {}, item.name),
              el('dd', { class: 'text-body-secondary small' },
                item.why, el('br', {}), `Conservation : ${item.retention}`),
            ]),
          ),
        ),
        el('div', { class: 'mt-4' },
          card('Ce que nous ne collectons pas',
            el('ul', { class: 'mb-0' },
              summary.not_collected.map((line) => el('li', {}, line))),
          ),
        ),
      ),

      el('div', { class: 'col-12 col-lg-5' },
        card('Tes droits',
          el('dl', { class: 'mb-0' },
            summary.rights.map((right) => [
              el('dt', {}, right.name),
              el('dd', { class: 'text-body-secondary small' }, right.how),
            ]),
          ),
        ),
        user
          ? el('div', { class: 'mt-4' }, actionsCard(context))
          : el('p', { class: 'form-text mt-3' },
            'Connecte-toi pour exporter, anonymiser ou supprimer tes donnees.'),
      ),
    ),
  );
}

function actionsCard(context) {
  const { user } = getState();

  return card('Exercer mes droits',
    el('p', { class: 'form-text mt-0' },
      'L’export est immediat. L’anonymisation et la suppression sont '
      + 'definitives : elles ne peuvent pas etre annulees.'),

    el('div', { class: 'd-grid gap-2' },


      el('a', {
        class: 'btn btn-outline-primary',
        href: '/api/me/data',
        download: 'mes-donnees.json',
      }, 'Telecharger toutes mes donnees'),

      dangerButton('Anonymiser mon compte',
        'Ton pseudo, ton e-mail, ton avatar et le contenu de tes messages sont '
        + 'effaces. Tes parties restent dans l’historique de tes adversaires, '
        + 'sous un nom neutre. Le compte devient inutilisable.',
        '/api/me/anonymize', context, user),

      dangerButton('Supprimer definitivement mon compte',
        'Le compte et toutes les donnees rattachees sont effaces. Aucune '
        + 'restauration n’est possible.',
        '/api/me/delete', context, user),
    ),
  );
}

function dangerButton(labelText, explanation, endpoint, context, user) {
  const container = el('div', {});

  const openForm = () => {
    const proof = user.has_password
      ? field('password', 'Mot de passe', { type: 'password', autocomplete: 'current-password' })
      : field('confirm', `Recopie ton pseudo (${user.display_name})`, { autocomplete: 'off' });
    const banner = el('div', { class: 'alert alert-danger d-none', role: 'alert' });

    container.replaceChildren(el('form', {
      class: 'border border-danger-subtle rounded p-3',
      novalidate: true,
      onSubmit: async (event) => {
        event.preventDefault();
        try {
          const body = user.has_password
            ? { password: proof.input.value }
            : { confirm: proof.input.value };
          await api(endpoint, { method: 'POST', body });
          clearSession();
          toast('Operation effectuee. Tu es deconnecte.', 'secondary');
          context.router.navigate('/');
        } catch (error) {
          banner.textContent = error.message;
          banner.classList.remove('d-none');
        }
      },
    },
      el('p', { class: 'small mb-2' }, explanation),
      banner,
      proof,
      el('div', { class: 'd-flex gap-2' },
        el('button', { class: 'btn btn-danger btn-sm', type: 'submit' }, 'Confirmer'),
        el('button', {
          class: 'btn btn-outline-secondary btn-sm',
          type: 'button',
          onClick: () => container.replaceChildren(trigger()),
        }, 'Annuler'),
      ),
    ));
  };

  const trigger = () => el('button', {
    class: 'btn btn-outline-danger w-100',
    type: 'button',
    onClick: openForm,
  }, labelText);

  container.appendChild(trigger());
  return container;
}
