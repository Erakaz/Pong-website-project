/**
 * Reglages du compte : identite, avatar, mot de passe, sessions.
 *
 * La double authentification et les options RGPD viennent s'ajouter ici aux
 * phases suivantes ; la structure en cartes independantes est prevue pour ca.
 */

import { api, post } from '../api.js';
import { el } from '../dom.js';
import { clearSession, getState, setSession, setUser } from '../store.js';
import { applyFormError, avatar, card, field, pageHeader, toast } from '../ui.js';

export default function render(context) {
  const { user } = getState();
  if (!user) {
    context.router.navigate('/login?next=/settings', { replace: true });
    return el('div', {});
  }

  return el('div', {},
    pageHeader('Mon compte', { subtitle: 'Identite, avatar et securite.' }),
    el('div', { class: 'row g-4' },
      el('div', { class: 'col-12 col-lg-6' },
        identityCard(),
        el('div', { class: 'mt-4' }, avatarCard()),
      ),
      el('div', { class: 'col-12 col-lg-6' },
        passwordCard(),
        el('div', { class: 'mt-4' }, twofaCard()),
        el('div', { class: 'mt-4' }, oauth42Card()),
        el('div', { class: 'mt-4' }, sessionsCard(context)),
      ),
    ),
  );
}

/* --- Double authentification --------------------------------------------- */

function twofaCard() {
  const body = el('div', {});
  const container = card('Double authentification', body);

  const paint = () => {
    const { user } = getState();
    body.replaceChildren(
      el('p', { class: 'form-text mt-0' },
        'Un code a usage unique, en plus du mot de passe, genere par une '
        + 'application d’authentification sur ton telephone.'),
      user.totp_enabled ? enabledView() : disabledView(),
    );
  };

  const enabledView = () => el('div', {},
    el('p', {}, el('span', { class: 'badge text-bg-success' }, 'Activee')),
    el('button', {
      class: 'btn btn-outline-danger btn-sm',
      type: 'button',
      onClick: () => body.replaceChildren(disableForm()),
    }, 'Desactiver'),
  );

  const disableForm = () => {
    const { user } = getState();
    const proof = field(user.has_password ? 'password' : 'code',
      user.has_password ? 'Mot de passe' : 'Code de ton application',
      { type: user.has_password ? 'password' : 'text', autocomplete: 'off' });
    const banner = el('div', { class: 'alert alert-danger d-none', role: 'alert' });

    return el('form', {
      novalidate: true,
      onSubmit: async (event) => {
        event.preventDefault();
        try {
          const payload = user.has_password
            ? { password: proof.input.value }
            : { code: proof.input.value };
          const data = await post('/api/me/2fa/disable', payload);
          setUser(data.user);
          toast('Double authentification desactivee.', 'secondary');
          paint();
        } catch (error) {
          applyFormError(error, { [user.has_password ? 'password' : 'code']: proof }, banner);
        }
      },
    },
      banner,
      el('p', { class: 'form-text mt-0' },
        'Confirme ton identite pour retirer ce facteur de securite.'),
      proof,
      el('div', { class: 'd-flex gap-2' },
        el('button', { class: 'btn btn-danger btn-sm', type: 'submit' }, 'Confirmer'),
        el('button', {
          class: 'btn btn-outline-secondary btn-sm', type: 'button', onClick: paint,
        }, 'Annuler'),
      ),
    );
  };

  const disabledView = () => el('div', {},
    el('p', {}, el('span', { class: 'badge text-bg-secondary' }, 'Desactivee')),
    el('button', {
      class: 'btn btn-primary btn-sm',
      type: 'button',
      onClick: async (event) => {
        event.currentTarget.disabled = true;
        try {
          const setup = await post('/api/me/2fa/setup', {});
          body.replaceChildren(await setupView(setup, paint));
        } catch (error) {
          toast(error.message, 'danger');
          event.currentTarget.disabled = false;
        }
      },
    }, 'Activer'),
  );

  paint();
  return container;
}

async function setupView(setup, done) {
  const qrHolder = el('div', {
    class: 'd-flex justify-content-center bg-white rounded p-2 mb-3',
    style: { 'min-height': '13rem' },
  });

  // Le QR est dessine dans le navigateur a partir de l'URI recue : le secret
  // n'est jamais envoye a un generateur de QR tiers.
  import('../qr.js')
    .then(({ renderQr }) => renderQr(setup.otpauth_uri))
    .then((svg) => qrHolder.replaceChildren(svg))
    .catch(() => qrHolder.replaceChildren(
      el('p', { class: 'text-dark small m-2' },
        'QR indisponible : saisis le code manuellement ci-dessous.')));

  const codeField = field('code', 'Code affiche par l’application', {
    inputmode: 'numeric', autocomplete: 'one-time-code', maxlength: 16,
  });
  const banner = el('div', { class: 'alert alert-danger d-none', role: 'alert' });

  return el('div', {},
    el('ol', { class: 'form-text ps-3' },
      el('li', {}, 'Scanne ce QR code avec ton application d’authentification.'),
      el('li', {}, 'Saisis le code a six chiffres qu’elle affiche.'),
    ),
    qrHolder,
    el('details', { class: 'mb-3' },
      el('summary', { class: 'form-text' }, 'Saisir le code manuellement'),
      el('code', { class: 'user-select-all d-block mt-2 text-break' }, setup.secret),
    ),
    el('form', {
      novalidate: true,
      onSubmit: async (event) => {
        event.preventDefault();
        try {
          const data = await post('/api/me/2fa/enable', { code: codeField.input.value });
          setSession({
            accessToken: data.access_token,
            expiresIn: data.expires_in,
            user: data.user,
          });
          showBackupCodes(data.backup_codes);
          done();
        } catch (error) {
          applyFormError(error, { code: codeField }, banner);
        }
      },
    },
      banner,
      codeField,
      el('button', { class: 'btn btn-primary btn-sm', type: 'submit' }, 'Activer'),
    ),
  );
}

function showBackupCodes(codes) {
  // Seule occasion de les voir : ils ne sont stockes que haches cote serveur.
  const dialog = el('div', {
    class: 'alert alert-warning position-fixed top-50 start-50 translate-middle shadow-lg',
    role: 'alertdialog',
    style: { 'z-index': '1090', 'max-width': '28rem' },
  },
    el('h2', { class: 'h6' }, 'Codes de secours'),
    el('p', { class: 'small' },
      'Note-les maintenant : ils ne seront plus jamais affiches. Chacun ne '
      + 'fonctionne qu’une fois, si tu perds ton telephone.'),
    el('ul', { class: 'list-unstyled font-monospace mb-3' },
      codes.map((code) => el('li', {}, code))),
    el('button', {
      class: 'btn btn-sm btn-dark',
      type: 'button',
      onClick: (event) => event.currentTarget.closest('[role="alertdialog"]').remove(),
    }, 'J’ai note ces codes'),
  );
  document.body.appendChild(dialog);
}

/* --- Compte 42 ------------------------------------------------------------ */

function oauth42Card() {
  const { user, features } = getState();
  if (!features.oauth42) return el('div', { class: 'd-none' });

  if (user.oauth42_login) {
    return card('Compte 42',
      el('p', { class: 'mb-0' },
        'Lie a ', el('strong', {}, user.oauth42_login), '.'),
    );
  }

  return card('Compte 42',
    el('p', { class: 'form-text mt-0' },
      'Associe ton compte de l’intra 42 pour pouvoir te connecter en un clic.'),
    el('button', {
      class: 'btn btn-outline-light btn-sm',
      type: 'button',
      onClick: async (event) => {
        event.currentTarget.disabled = true;
        try {
          // Route authentifiee : c'est elle qui lie le parcours OAuth a ce
          // compte precis, sans faire confiance a un parametre d'URL.
          const data = await post('/api/me/oauth42/link', {});
          window.location.assign(data.authorize_url);
        } catch (error) {
          toast(error.message, 'danger');
          event.currentTarget.disabled = false;
        }
      },
    }, 'Lier mon compte 42'),
  );
}

/* --- Identite ------------------------------------------------------------ */

function identityCard() {
  const { user } = getState();

  // Les cles portent exactement les noms de champs renvoyes par le serveur en
  // cas d'erreur : `applyFormError` peut ainsi poser le message sur le bon
  // champ sans table de correspondance.
  const fields = {
    display_name: field('display_name', 'Pseudo', {
      value: user.display_name, maxlength: 24, autocomplete: 'nickname',
    }),
    email: field('email', 'Adresse e-mail', {
      type: 'email', value: user.email || '', autocomplete: 'email',
    }),
  };

  const banner = el('div', { class: 'alert alert-danger d-none', role: 'alert' });
  const submit = el('button', { class: 'btn btn-primary', type: 'submit' }, 'Enregistrer');

  const form = el('form', {
    novalidate: true,
    onSubmit: async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const data = await api('/api/me', {
          method: 'PATCH',
          body: {
            display_name: fields.display_name.input.value,
            email: fields.email.input.value,
          },
        });
        setUser(data.user);
        toast('Profil mis a jour.', 'success');
        banner.classList.add('d-none');
      } catch (error) {
        applyFormError(error, fields, banner);
      } finally {
        submit.disabled = false;
      }
    },
  }, banner, fields.display_name, fields.email, submit);

  return card('Identite', form);
}

/* --- Avatar -------------------------------------------------------------- */

function avatarCard() {
  const { user } = getState();
  const preview = avatar(user, 96);
  const input = el('input', {
    class: 'form-control',
    type: 'file',
    id: 'settings-avatar',
    accept: 'image/png,image/jpeg,image/webp,image/gif',
  });

  const upload = async () => {
    const file = input.files && input.files[0];
    if (!file) return;

    // Apercu immediat avec une URL blob : la CSP autorise `blob:` en source
    // d'image precisement pour ce cas.
    const objectUrl = URL.createObjectURL(file);
    preview.src = objectUrl;

    const formData = new FormData();
    formData.append('avatar', file);
    try {
      const data = await api('/api/me/avatar', { method: 'POST', formData });
      setUser(data.user);
      preview.src = data.user.avatar_url;
      toast('Avatar mis a jour.', 'success');
    } catch (error) {
      preview.src = getState().user.avatar_url;
      toast(error.message, 'danger');
    } finally {
      URL.revokeObjectURL(objectUrl);
      input.value = '';
    }
  };

  const remove = async () => {
    try {
      const data = await api('/api/me/avatar', { method: 'DELETE' });
      setUser(data.user);
      preview.src = data.user.avatar_url;
    } catch (error) {
      toast(error.message, 'danger');
    }
  };

  input.addEventListener('change', upload);

  return card('Avatar',
    el('div', { class: 'd-flex align-items-center gap-3 mb-3' },
      preview,
      el('p', { class: 'form-text mb-0' },
        'PNG, JPEG, WebP ou GIF, 2 Mo maximum. L’image est recadree en carre, '
        + 're-encodee et ses metadonnees sont supprimees.'),
    ),
    el('label', { class: 'form-label', for: 'settings-avatar' }, 'Choisir une image'),
    input,
    el('button', {
      class: 'btn btn-outline-secondary btn-sm mt-3',
      type: 'button',
      onClick: remove,
    }, 'Retirer l’avatar'),
  );
}

/* --- Mot de passe -------------------------------------------------------- */

function passwordCard() {
  const { user } = getState();

  const fields = {
    current_password: field('current_password', 'Mot de passe actuel', {
      type: 'password', autocomplete: 'current-password', required: user.has_password,
    }),
    password: field('password', 'Nouveau mot de passe', {
      type: 'password', autocomplete: 'new-password',
      help: 'Au moins 10 caracteres.',
    }),
  };

  const banner = el('div', { class: 'alert alert-danger d-none', role: 'alert' });
  const submit = el('button', { class: 'btn btn-primary', type: 'submit' }, 'Changer');

  const form = el('form', {
    novalidate: true,
    onSubmit: async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        await post('/api/me/password', {
          current_password: fields.current_password.input.value,
          password: fields.password.input.value,
        });
        toast('Mot de passe change. Les autres sessions ont ete fermees.', 'success');
        fields.current_password.input.value = '';
        fields.password.input.value = '';
        banner.classList.add('d-none');
      } catch (error) {
        applyFormError(error, fields, banner);
      } finally {
        submit.disabled = false;
      }
    },
  },
    banner,
    user.has_password
      ? fields.current_password
      : el('p', { class: 'form-text' },
        'Ce compte a ete cree via 42 : tu peux definir un mot de passe pour '
        + 'pouvoir aussi te connecter classiquement.'),
    fields.password,
    submit,
  );

  return card('Mot de passe', form);
}

/* --- Sessions ------------------------------------------------------------ */

function sessionsCard(context) {
  return card('Sessions',
    el('p', { class: 'form-text' },
      'Ferme toutes les sessions ouvertes, sur cet appareil comme sur les autres. '
      + 'A utiliser si tu penses que quelqu’un a acces a ton compte.'),
    el('button', {
      class: 'btn btn-outline-danger',
      type: 'button',
      onClick: async (event) => {
        event.currentTarget.disabled = true;
        try {
          await post('/api/auth/logout-all', {}, { csrf: true });
        } catch {
          // Meme si l'appel echoue, on deconnecte localement : l'utilisateur
          // ne doit jamais rester coince sur un ecran connecte.
        }
        clearSession();
        context.router.navigate('/');
      },
    }, 'Se deconnecter partout'),
  );
}
