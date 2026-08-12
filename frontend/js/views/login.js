import { post } from '../api.js';
import { el } from '../dom.js';
import { getState, setSession } from '../store.js';
import { applyFormError, card, field, pageHeader } from '../ui.js';

export default function render(context) {
  const { features } = getState();

  const fields = {
    email: field('email', 'Adresse e-mail', { type: 'email', autocomplete: 'username' }),
    password: field('password', 'Mot de passe', {
      type: 'password', autocomplete: 'current-password',
    }),
  };

  const banner = el('div', { class: 'alert alert-danger d-none', role: 'alert' });
  const submit = el('button', { class: 'btn btn-primary w-100', type: 'submit' },
    'Se connecter');

  const form = el('form', {
    novalidate: true,
    onSubmit: async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const data = await post('/api/auth/login', {
          email: fields.email.input.value,
          password: fields.password.input.value,
        }, { auth: false });

        if (data.twofa_required) {


          window.sessionStorage.setItem('ftt_twofa', data.twofa_token);
          context.router.navigate('/login/2fa');
          return;
        }

        setSession({
          accessToken: data.access_token,
          expiresIn: data.expires_in,
          user: data.user,
        });
        context.router.navigate(context.query.get('next') || '/');
      } catch (error) {
        applyFormError(error, fields, banner);
        submit.disabled = false;
      }
    },
  },
    banner,
    fields.email,
    fields.password,
    submit,
  );

  return el('div', { class: 'row justify-content-center' },
    el('div', { class: 'col-12 col-md-8 col-lg-5' },
      pageHeader('Connexion'),
      card(null,
        form,
        features.oauth42 ? oauthBlock() : null,
        el('p', { class: 'text-center mb-0 mt-3' },
          'Pas encore de compte ? ',
          el('a', { href: '/register' }, 'Creer un compte')),
      ),
    ),
  );
}

function oauthBlock() {
  return el('div', {},
    el('div', { class: 'd-flex align-items-center gap-3 my-3 text-body-secondary' },
      el('hr', { class: 'flex-grow-1 m-0' }),
      el('span', { class: 'small' }, 'ou'),
      el('hr', { class: 'flex-grow-1 m-0' }),
    ),


    el('a', {
      class: 'btn btn-outline-light w-100',
      href: '/api/auth/oauth42/login',
    }, 'Se connecter avec 42'),
  );
}
