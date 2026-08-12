# ft_transcendence

Site web de tournois **Pong** — projet final du tronc commun 42 (sujet v15).

Toute la stack demarre en **une seule commande** :

```bash
docker compose up --build
```

Puis ouvrir **<https://localhost:8443>**. Le certificat est auto-signe :
l'avertissement du navigateur au premier acces est attendu.

---

## Sommaire

- [Demarrage rapide](#demarrage-rapide)
- [Modules du sujet couverts](#modules-du-sujet-couverts)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Developpement](#developpement)
- [Tests](#tests)
- [Depannage](#depannage)

---

## Demarrage rapide

**Prerequis** : Docker avec Compose v2. Rien d'autre — ni Python, ni Node, ni
PostgreSQL sur la machine hote.

```bash
cp .env.example .env
python3 tools/gen_secrets.py .env    # remplace les valeurs « change-me »
docker compose up --build
```

Quatre services demarrent :

| Service    | Role                                                        | Expose |
|------------|-------------------------------------------------------------|--------|
| `nginx`    | TLS, frontend statique, reverse proxy HTTP et WSS            | 8080, 8443 |
| `backend`  | Django + Channels servis par Daphne (HTTP + WebSocket)       | interne |
| `postgres` | Base de donnees                                              | interne |
| `redis`    | Channel layer, presence en ligne, compteurs de rate-limit    | interne |

Seul `nginx` publie des ports. PostgreSQL et Redis sont sur un reseau Docker
`internal` : ils ne sont joignables ni depuis l'hote, ni depuis nginx.

> **Ports > 1024 volontairement.** Sur les machines de l'ecole, Docker tourne
> en mode *rootless* et ne peut pas ecouter sur 80 / 443.

Un raccourci `make` existe pour chaque operation courante :

```bash
make          # liste les cibles disponibles
make up       # docker compose up --build
make test     # suite de tests dans le conteneur backend
make fclean   # tout supprimer, volumes compris
```

---

## Modules du sujet couverts

Partie obligatoire **+ 9 modules majeurs equivalents** (7 requis pour 100 %).

| Section            | Module                                            | Poids   |
|--------------------|---------------------------------------------------|---------|
| Web                | Framework backend — **Django**                    | Majeur  |
| Web                | Toolkit frontend — **Bootstrap**                   | Mineur  |
| Web                | Base de donnees — **PostgreSQL**                   | Mineur  |
| User Management    | Gestion des utilisateurs et authentification       | Majeur  |
| User Management    | Authentification distante — **OAuth 2.0 avec 42**  | Majeur  |
| Gameplay           | Joueurs distants                                   | Majeur  |
| Gameplay           | Messagerie en direct                               | Majeur  |
| AI-Algo            | Tableaux de bord statistiques                      | Mineur  |
| Cybersecurity      | Double authentification (2FA) et JWT               | Majeur  |
| Cybersecurity      | Conformite RGPD                                    | Mineur  |
| Server-Side Pong   | Pong cote serveur et API                           | Majeur  |

Soit **7 majeurs + 4 mineurs = 9 majeurs equivalents**.

Le detail des choix techniques et leur justification pour la soutenance sont
dans [`docs/decisions.md`](docs/decisions.md).

---

## Architecture

```
navigateur ──HTTPS/WSS──▶ nginx ──HTTP/WS──▶ Daphne (Django + Channels)
                            │                        │
                     frontend statique          PostgreSQL   Redis
```

- **Frontend** : JavaScript vanilla en modules ES, sans etape de build. Le
  routeur s'appuie sur l'History API ; nginx renvoie `index.html` pour toute
  URL inconnue, donc les boutons Precedent / Suivant et le rechargement direct
  d'une URL profonde fonctionnent.
- **Backend** : Django sans Django REST Framework — vues JSON et validation
  ecrites a la main, pour garder le controle complet sur la validation serveur
  exigee par le sujet.
- **Jeu** : la physique tourne **cote serveur** a 60 Hz (module *Server-Side
  Pong*). Le client n'envoie que des inputs et n'affiche que des instantanes
  interpoles — un client modifie ne peut donc pas tricher.

```
backend/
├── config/     reglages, routage HTTP et WebSocket, point d'entree ASGI
├── core/       helpers JSON, validation, middlewares transverses
├── accounts/   comptes, JWT, 2FA, OAuth 42, amis, RGPD
├── game/       moteur Pong, boucle de partie, matchs, tournois, API
└── chat/       messagerie directe, blocages, invitations, presence
frontend/
├── js/         routeur, client API, vues, moteur de rendu du jeu
├── css/        surcouche de Bootstrap
└── vendor/     Bootstrap vendorise (la CSP interdit tout CDN)
```

---

## Configuration

Tout passe par `.env`, ignore par git. `.env.example` documente chaque
variable. **Aucun secret n'est commite** — le sujet sanctionne la publication
de credentials par un echec du projet.

### Activer la connexion 42 (optionnel)

Le module fonctionne sans configuration : le bouton reste simplement masque.
Pour l'activer :

1. creer une application sur <https://profile.intra.42.fr/oauth/applications> ;
2. renseigner comme *redirect URI* exactement
   `https://localhost:8443/api/auth/oauth42/callback` ;
3. reporter `OAUTH42_UID` et `OAUTH42_SECRET` dans `.env` ;
4. `docker compose up --build`.

---

## Developpement

Le mode developpement ajoute des *bind-mounts* pour recharger le code sans
reconstruire l'image :

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
# ou simplement :  make dev
```

> Ces bind-mounts sont **interdits sur les machines 42** (Docker rootless avec
> un UID non-root dans le conteneur), d'ou leur isolement dans un fichier
> separe : le `docker-compose.yml` de rendu n'utilise que des volumes nommes.

---

## Tests

```bash
make test          # ou : docker compose exec backend python manage.py test
```

La suite couvre la physique du jeu, la generation des brackets, les JWT, le
TOTP (vecteurs de test officiels de la RFC 6238), l'application des blocages
dans le chat et les cascades RGPD.

---

## Depannage

**Le navigateur affiche un avertissement de securite.**
Attendu : le certificat est auto-signe. « Parametres avances » puis
« Continuer vers localhost ».

**Le port 8443 est deja utilise.**
Changer `HTTPS_PORT` (et `HTTP_PORT`) dans `.env`, puis relancer.

**HSTS bloque mes autres projets locaux en HTTP.**
nginx envoie `Strict-Transport-Security`, qui s'applique a l'hote `localhost`
tous ports confondus. Pour l'annuler : ouvrir `chrome://net-internals/#hsts`,
saisir `localhost` dans *Delete domain security policies*. Pour l'eviter
pendant le developpement, commenter la ligne `add_header
Strict-Transport-Security` dans `nginx/nginx.conf`.

**Repartir de zero (base de donnees comprise).**

```bash
make fclean && make up
```
