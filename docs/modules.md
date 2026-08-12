# Couverture du sujet

Sujet ft_transcendence version 15.

## Partie obligatoire

| Exigence | Ou elle est traitee |
|---|---|
| Partie en direct, deux joueurs, meme clavier | `frontend/js/game/input.js`, `backend/game/engine.py` |
| Tournoi a plusieurs joueurs | `backend/game/bracket.py`, `backend/game/services.py` |
| Affichage des rencontres et de leur ordre | `frontend/js/views/tournament.js` |
| Alias saisis au demarrage, remis a zero ensuite | modele `TournamentPlayer` |
| Matchmaking et annonce du prochain match | `Tournament.next_match`, `backend/game/notifications.py` |
| Vitesse de raquette identique pour tous | constante `PADDLE_SPEED` |
| Essence du Pong de 1972 | `frontend/js/game/renderer.js` |
| Application monopage, Precedent et Suivant | `frontend/js/router.js` |
| Aucune erreur en console | voir docs/decisions.md |
| Lancement en une commande | `docker-compose.yml` |
| Mots de passe haches | Argon2id |
| Protection contre les injections SQL et XSS | ORM Django, `js/dom.js`, politique CSP |
| HTTPS et WSS | `nginx/nginx.conf` |
| Validation de toutes les entrees | `backend/core/validation.py` |
| Routes protegees | decorateur `login_required` |
| Secrets hors du depot | `.gitignore` |

## Modules

Sept majeurs et quatre mineurs, soit neuf majeurs equivalents. Le seuil pour
100 % est de sept.

### Web

**Framework backend, Django.** Tout le dossier `backend/`.

**Toolkit frontend, Bootstrap.** Vendorise dans `frontend/vendor/bootstrap/`.
Seules ses variables CSS sont redefinies.

**Base de donnees, PostgreSQL.** Unique base du projet.

### User Management

**Gestion des utilisateurs et authentification.** Inscription, connexion,
pseudo unique, modification du profil, avatar, amis avec statut en ligne,
statistiques et historique des matchs. La politique de doublons est justifiee
dans docs/decisions.md.

**Authentification distante avec 42.** Flux OAuth complet dans
`accounts/oauth42.py`. Le module reste inactif tant que les identifiants ne
sont pas renseignes : le bouton est masque et les routes repondent 503.

### Gameplay

**Joueurs distants.** `game/rooms.py`, `game/consumers.py`,
`frontend/js/game/net.js`. Interpolation, prediction locale, pause a la
deconnexion, reconnexion, forfait.

**Messagerie en direct.** Messages directs, blocage applique par le serveur,
invitation a jouer, annonces du systeme de tournoi, acces au profil depuis la
conversation.

### AI-Algo

**Tableaux de bord.** `game/stats.py` et `frontend/js/charts.js`. Un tableau
par joueur et un par partie. Les graphiques sont en SVG ecrit a la main, et les
memes chiffres sont toujours disponibles en texte.

Le module d'adversaire automatique n'est pas realise.

### Cybersecurity

**Double authentification et JWT.** JWT et TOTP ecrits a la main, codes de
secours a usage unique, connexion en deux etapes. Les tests verifient
l'implementation TOTP contre les vecteurs de la RFC 6238.

**Conformite RGPD.** Export des donnees, anonymisation, suppression definitive,
page d'information.

### Server-Side Pong

**Pong cote serveur et API.** La physique est entierement sur le serveur.
L'API permet de jouer sans navigateur :

```
curl -k https://localhost:8443/api/games/<id>/state
curl -k -X POST https://localhost:8443/api/games/<id>/input \
     -H 'Content-Type: application/json' -d '{"side":0,"dir":-1}'
```
