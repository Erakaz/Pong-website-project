import { post } from '../api.js';
import { el } from '../dom.js';
import { setSession } from '../store.js';
import { applyFormError, card, field, pageHeader } from '../ui.js';

export default function render(context) {
  const fields = {
    display_name: field('display_name', 'Pseudo', {
      autocomplete: 'nickname',
      maxlength: 24,
      help: 'De 3 a 24 caracteres. C’est le nom vu par les autres joueurs et '
        + 'affiche dans les tournois.',
    }),
    email: field('email', 'Adresse e-mail', { type: 'email', autocomplete: 'username' }),
    password: field('password', 'Mot de passe', {
      type: 'password',
      autocomplete: 'new-password',
      help: 'Au moins 10 caracteres, et pas un mot de passe courant.',
    }),
  };

  const banner = el('div', { class: 'alert alert-danger d-none', role: 'alert' });
  const submit = el('button', { class: 'btn btn-primary w-100', type: 'submit' },
    'Creer mon compte');

  const form = el('form', {
    novalidate: true,
    onSubmit: async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const data = await post('/api/auth/register', {
          display_name: fields.display_name.input.value,
          email: fields.email.input.value,
          password: fields.password.input.value,
        }, { auth: false });

        setSession({
          accessToken: data.access_token,
          expiresIn: data.expires_in,
          user: data.user,
        });
        context.router.navigate('/');
      } catch (error) {
        applyFormError(error, fields, banner);
        submit.disabled = false;
      }
    },
  },
    banner,
    fields.display_name,
    fields.email,
    fields.password,
    submit,
  );

  return el('div', { class: 'row justify-content-center' },
    el('div', { class: 'col-12 col-md-8 col-lg-5' },
      pageHeader('Creer un compte'),
      card(null,
        form,
        el('p', { class: 'text-center mb-0 mt-3' },
          'Deja inscrit ? ', el('a', { href: '/login' }, 'Se connecter')),
      ),
    ),
  );
}
