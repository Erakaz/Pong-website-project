# Couverture du sujet, exigence par exigence

Sujet ft_transcendence version 15. Pour chaque point, ou le verifier dans le
code et comment le constater a l'ecran.

---

## Partie obligatoire

| Exigence du sujet | Ou c'est fait | Comment le verifier |
|---|---|---|
| Site de tournois Pong | tout le projet | `https://localhost:8443` |
| Partie en direct contre un autre joueur, **meme clavier** | `frontend/js/game/input.js`, `game/engine.py` | *Jouer* → *Partie a deux, meme clavier*. W/S et ↑/↓ |
| Tournoi a plusieurs joueurs, chacun son tour | `game/bracket.py`, `game/services.py` | *Jouer* → *Tournoi local* |
| Affichage clair de qui joue contre qui, et de l'ordre | `frontend/js/views/tournament.js` | Le tableau complet, tour par tour, des l'ouverture |
| Saisie des alias au demarrage, remis a zero au tournoi suivant | `TournamentPlayer`, `_parse_aliases` | Les alias appartiennent au tournoi et disparaissent avec lui |
| Systeme de matchmaking annoncant le prochain combat | `Tournament.next_match`, `game/notifications.py` | Bandeau « Prochaine rencontre » + message systeme dans le chat |
| Regles identiques pour tous, **meme vitesse de raquette** | `engine.PADDLE_SPEED` | Constante unique. Test : `test_both_paddles_move_at_the_same_speed` |
| Essence du Pong de 1972 | `frontend/js/game/renderer.js` | Balle carree, filet en pointilles, score en gros chiffres |
| Application monopage, Precedent / Suivant fonctionnels | `frontend/js/router.js` + `try_files` nginx | Naviguer puis utiliser les fleches du navigateur |
| Dernier Chrome stable | — | Teste sur Chrome |
| Aucune erreur, aucun avertissement en console | voir `docs/decisions.md` §5 | Ouvrir la console et parcourir le site |
| Lancement en une seule commande | `docker-compose.yml` | `docker compose up --build` |
| Mots de passe haches | `PASSWORD_HASHERS` (Argon2id) | Test : `test_password_is_hashed_with_argon2` |
| Protection SQLi / XSS | ORM seul ; `js/dom.js` ; CSP | `docs/decisions.md` §4 |
| HTTPS et WSS partout | `nginx/nginx.conf` | Page *Diagnostic* |
| Validation de toutes les entrees, cote serveur | `core/validation.py` | Tests de validation des formulaires |
| Routes API protegees | `core.http.login_required` | Tests `..._route_is_protected` |
| Secrets dans `.env`, ignore par git | `.env.example`, `.gitignore` | `git status` ne montre jamais `.env` |

---

## Modules — 7 majeurs + 4 mineurs = 9 majeurs equivalents

### Web

**Majeur — Framework backend (Django).**
`backend/` en entier. Django 5 en ASGI, servi par Daphne.

**Mineur — Toolkit frontend (Bootstrap).**
`frontend/vendor/bootstrap/`, vendorise. Toute l'interface s'appuie dessus ;
`css/app.css` ne fait qu'ajouter l'identite Pong.

**Mineur — Base de donnees (PostgreSQL).**
`docker-compose.yml`, `config/settings.py`. Seule base du projet.

### User Management

**Majeur — Gestion des utilisateurs et authentification.**
`accounts/views.py`, `accounts/models.py`.
Inscription et connexion securisees, pseudo unique, modification du profil,
avatar avec valeur par defaut, amis et statut en ligne, statistiques de
victoires et defaites, historique des matchs date. Politique de doublons
justifiee dans `docs/decisions.md` §3.

**Majeur — Authentification distante (OAuth 2.0 avec 42).**
`accounts/oauth42.py`, `accounts/views_auth2.py`.
Flux complet avec `state`, echange serveur a serveur, creation ou liaison de
compte. **Inactif tant que `.env` ne contient pas les credentials** : le bouton
est masque et les routes repondent 503.

### Gameplay and user experience

**Majeur — Joueurs distants.**
`game/rooms.py`, `game/consumers.py`, `frontend/js/game/net.js`.
Deux machines, une partie. Interpolation, prediction locale, pause a la
deconnexion, reconnexion, forfait apres 20 secondes. Tests :
`game/tests/test_match_socket.py`.

**Majeur — Messagerie en direct.**
`chat/`, `accounts/consumers.py`, `frontend/js/views/chat.js`.
Messages directs, blocage applique cote serveur, invitation a jouer depuis la
conversation, annonces du systeme de tournoi, acces au profil depuis le fil.

### AI-Algo

**Mineur — Tableaux de bord.**
`game/stats.py`, `frontend/js/charts.js`, vues `dashboard` et `match`.
Tableau de bord joueur (bilan, evolution, face a face) et tableau de bord de
partie (deroule du score point par point). Graphiques SVG ecrits a la main,
toujours doubles des chiffres en toutes lettres.

> Le module *AI Opponent* n'est volontairement pas realise. Le moteur
> autoritatif laisse une couture propre pour l'ajouter : un « joueur » IA qui
> pousse des inputs a 1 Hz dans la boucle, sans rien changer d'autre.

### Cybersecurity

**Majeur — Double authentification et JWT.**
`accounts/jwt_utils.py`, `accounts/totp.py`, `accounts/views_auth2.py`.
JWT HS256 et TOTP RFC 6238 ecrits a la main. Codes de secours a usage unique.
Connexion en deux temps. Tests contre les vecteurs officiels de la RFC.

**Mineur — Conformite RGPD.**
`accounts/gdpr.py`, `accounts/views_gdpr.py`, page `/privacy`.
Export JSON complet, anonymisation, suppression definitive, information claire
sur les droits.

### Server-Side Pong

**Majeur — Pong cote serveur et API.**
`game/engine.py`, `game/rooms.py`, `game/views.py`.
Toute la physique est sur le serveur. L'API expose les ressources du jeu et
permet d'y jouer sans navigateur :

```bash
curl -k https://localhost:8443/api/games/<id>/state
curl -k -X POST https://localhost:8443/api/games/<id>/input \
     -H 'Content-Type: application/json' -d '{"side":0,"dir":-1}'
```

---

## Recapitulatif

| Poids | Nombre | Equivalent majeur |
|---|---|---|
| Modules majeurs | 7 | 7 |
| Modules mineurs | 4 | 2 |
| **Total** | | **9** |

Seuil requis pour 100 % : **7 majeurs**.
