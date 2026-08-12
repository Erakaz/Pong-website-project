/**
 * Seconde etape de la connexion : le code a usage unique.
 *
 * On arrive ici avec un jeton intermediaire de 5 minutes, place en
 * sessionStorage par la vue de connexion. Ce jeton n'ouvre aucune route de
 * l'API : il ne sert qu'a prouver, a cet endpoint precis, que le mot de passe
 * a bien ete verifie juste avant.
 */

import { post } from '../api.js';
import { el } from '../dom.js';
import { setSession } from '../store.js';
import { applyFormError, card, field, pageHeader } from '../ui.js';

const TOKEN_KEY = 'ftt_twofa';

export default function render(context) {
  const token = window.sessionStorage.getItem(TOKEN_KEY);
  if (!token) {
    context.router.navigate('/login', { replace: true });
    return el('div', {});
  }

  const fields = {
    code: field('code', 'Code a six chiffres', {
      inputmode: 'numeric',
      autocomplete: 'one-time-code',
      maxlength: 16,
      pattern: '[0-9 ]*',
      help: 'Le code affiche par ton application d’authentification. '
        + 'Un code de secours fonctionne aussi.',
    }),
  };
  fields.code.input.setAttribute('autofocus', '');

  const banner = el('div', { class: 'alert alert-danger d-none', role: 'alert' });
  const submit = el('button', { class: 'btn btn-primary w-100', type: 'submit' }, 'Valider');

  const form = el('form', {
    novalidate: true,
    onSubmit: async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const data = await post('/api/auth/2fa/verify', {
          twofa_token: token,
          code: fields.code.input.value,
        }, { auth: false });

        window.sessionStorage.removeItem(TOKEN_KEY);
        setSession({
          accessToken: data.access_token,
          expiresIn: data.expires_in,
          user: data.user,
        });
        context.router.navigate('/');
      } catch (error) {
        if (error.code === 'invalid_twofa_token') {
          window.sessionStorage.removeItem(TOKEN_KEY);
          context.router.navigate('/login?expired=1');
          return;
        }
        applyFormError(error, fields, banner);
        submit.disabled = false;
      }
    },
  }, banner, fields.code, submit);

  return el('div', { class: 'row justify-content-center' },
    el('div', { class: 'col-12 col-md-8 col-lg-5' },
      pageHeader('Verification en deux etapes', {
        subtitle: 'Ton mot de passe est correct. Il reste a confirmer avec ton '
          + 'application d’authentification.',
      }),
      card(null, form,
        el('p', { class: 'text-center mb-0 mt-3' },
          el('a', { href: '/login' }, 'Revenir a la connexion')),
      ),
    ),
  );
}
