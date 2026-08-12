# Choix techniques et justifications

Le sujet est explicite : « All your choices must be justifiable » et « During
the evaluation, the team will justify any usage of library or tool that is not
explicitly approved by the subject ». Ce document rassemble les decisions et
leur raison d'etre, dans l'ordre ou un evaluateur les rencontrera.

---

## 1. Dependances

### Ce que le projet utilise

| Dependance | Role | Pourquoi elle est admissible |
|---|---|---|
| **Django** | Framework backend | Impose par le module *Framework as backend* |
| **Channels** + **Daphne** | WebSocket / ASGI | Brique de transport, pas de logique metier. Sans WebSocket, ni parties a distance ni chat |
| **channels-redis** | Channel layer | Infrastructure de messagerie interne |
| **psycopg** | Pilote PostgreSQL | Impose par le module *Database* |
| **argon2-cffi** | Hachage des mots de passe | Le sujet exige « a strong password hashing algorithm » |
| **Pillow** | Re-encodage des avatars | Tache unique et bien delimitee : decoder puis re-encoder une image |
| **redis** | Compteurs de rate-limit | Client bas niveau |
| **Bootstrap** | Toolkit CSS | Impose par le module *front-end toolkit* |
| **qrcode-generator** | Matrice d'un QR code | Tache unique : calculer une matrice de modules. Le rendu SVG est ecrit ici (`js/qr.js`) |

### Ce que le projet refuse volontairement

| Ecartee | Pourquoi |
|---|---|
| **Django REST Framework** | Tiers, hors Django officiel. Les vues JSON et la validation sont ecrites a la main (`core/http.py`, `core/validation.py`) : le sujet exige une validation serveur maitrisee, autant l'ecrire |
| **PyJWT** | Emettre et verifier un JWT *est* l'objet du module 2FA/JWT. Delegue, il ne resterait rien a evaluer. Implemente dans `accounts/jwt_utils.py` |
| **pyotp** | Meme raison pour le TOTP. Implemente dans `accounts/totp.py`, valide contre les vecteurs officiels de la RFC 6238 |
| **django-allauth** | Resoudrait a lui seul le module *Remote authentication* : explicitement interdit. Le flux OAuth 42 est ecrit avec `urllib` (`accounts/oauth42.py`) |
| **requests / httpx** | `urllib` de la bibliotheque standard suffit pour deux appels HTTP |
| **Chart.js / D3** | Les tableaux de bord se contentent de trois formes, dessinees en SVG dans `js/charts.js` |
| **Un moteur de jeu** | La physique du Pong tient en 200 lignes (`game/engine.py`) et doit rester lisible pour etre defendue |

---

## 2. Architecture du jeu

### La physique tourne cote serveur

Les modules *Server-Side Pong* et *Remote players* sont concus ensemble : un
seul moteur, dans `game/engine.py`, pour la partie locale comme pour la partie
a distance. Le client n'envoie qu'une intention (`haut`, `bas`, `immobile`) et
n'affiche que des instantanes.

Consequences :

- **un client modifie ne peut pas tricher** : il n'a aucune position a
  falsifier, seulement une direction parmi trois, normalisee a la reception ;
- **la vitesse de raquette est une constante unique** (`PADDLE_SPEED`),
  partagee par les deux joueurs — l'exigence du sujet est structurelle, pas une
  promesse ;
- **un seul chemin de code** : local, a distance et tournoi se comportent
  identiquement.

### 60 Hz de simulation, 30 Hz de diffusion, 100 ms d'interpolation

Simuler a 60 Hz donne des rebonds stables. Diffuser a 30 Hz divise le trafic
par deux sans que l'oeil le voie. Le client affiche l'etat tel qu'il etait il y
a 100 ms, en interpolant entre deux instantanes **connus** : sans ce retard, une
trame en retard obligerait a extrapoler, et la balle sauterait a chaque
correction.

Sa propre raquette, elle, est **predite localement** (`renderer.js`) : sinon
appuyer sur une touche ne se verrait qu'apres un aller-retour reseau. L'ecart
avec le serveur est resorbe progressivement, ou d'un coup s'il devient grand.

### Sous-pas de collision

A pleine vitesse la balle parcourt environ 14 unites par tick, presque deux
rayons : sans decoupage du deplacement, elle traverserait une raquette d'un
tick a l'autre. `_move_ball` decoupe le pas de temps pour que la balle avance
au plus de trois quarts de rayon a la fois. Verifie par un test qui fait suivre
la balle par les deux raquettes pendant 60 secondes : aucun but ne doit etre
marque.

### L'etat des parties vit en memoire du process

`game/rooms.py` tient un registre en memoire. C'est assume : le projet lance un
seul conteneur `backend`, et l'etat d'une partie en cours n'a pas de raison de
survivre a son redemarrage. Passer a plusieurs workers demanderait de deplacer
la boucle dans un worker dedie, avec le channel layer comme unique canal.

### Deconnexions

Une coupure met la partie **en pause** — ni la balle ni les raquettes ne
bougent, pour ne pas avantager celui qui reste. Le joueur absent a 20 secondes
pour revenir ; au-dela, forfait enregistre avec `by_forfeit=True`. On reprend
toujours par un decompte, jamais balle en jeu.

---

## 3. Identite et doublons

> Le sujet demande explicitement de justifier ce point : « the management of
> duplicate usernames/emails is at your discretion. You must provide a
> justification for your decision. »

- **L'e-mail est unique** et sert d'ancre d'identite : c'est l'identifiant de
  connexion, et c'est lui qui permet de reconnaitre qu'un compte 42 et un
  compte mot de passe designent la meme personne.
- **Le `display_name` est unique separement.** C'est le nom public : celui du
  tableau de tournoi et du chat. Deux joueurs homonymes rendraient un bracket
  indechiffrable et l'usurpation triviale.
- **Un tournoi impose des alias distincts** (contrainte d'unicite en base sur
  `(tournoi, alias)`), pour la meme raison.
- **Un compte anonymise libere son pseudo et perd son e-mail** (`null=True`) :
  PostgreSQL autorise plusieurs `NULL` dans un index unique.

### Collision entre un compte 42 et un compte existant

Si l'e-mail renvoye par l'intra correspond deja a un compte cree par mot de
passe, **la connexion 42 est refusee**. L'utilisateur doit se connecter
normalement puis lier son compte 42 depuis ses reglages.

Lier automatiquement offrirait le compte a quiconque controle l'adresse e-mail
associee — c'est le scenario classique de prise de controle par fournisseur
d'identite. Le parcours de liaison, lui, part d'une route **authentifiee** qui
inscrit l'identifiant du compte dans le `state` OAuth : le callback sait a quel
compte rattacher le profil sans faire confiance a un parametre d'URL.

---

## 4. Securite

### Sessions : JWT court + refresh rotatif

| | Access token | Refresh token |
|---|---|---|
| Nature | JWT signe HS256 | Chaine aleatoire opaque |
| Duree | 15 minutes | 14 jours |
| Transport | En-tete `Authorization` | Cookie `httpOnly` |
| Stockage client | **Memoire JS uniquement** | Cookie, invisible du JS |
| Stockage serveur | Aucun | SHA-256 seulement |

Pourquoi l'access token n'est jamais dans `localStorage` : ce stockage est
lisible par n'importe quel script de la page, donc par une XSS. En memoire, il
disparait au rechargement — et c'est le cookie `httpOnly`, hors de portee du
JavaScript, qui permet de retrouver la session.

Pourquoi seul le SHA-256 du refresh token est stocke : une fuite de la base ne
permet alors pas de rejouer les sessions, exactement comme pour un mot de
passe. Un simple SHA-256 suffit ici la ou un mot de passe exige Argon2 — le
jeton fait 48 octets aleatoires, il n'est pas attaquable par dictionnaire.

**Rotation a usage unique avec detection de rejeu** : chaque rafraichissement
invalide l'ancien jeton. Si un jeton deja consomme est represente, c'est qu'il
a fuite : toute la chaine de la session est revoquee.

**Revocation globale par numero de generation** (`User.token_version`) plutot
que par horodatage : comparer une date a la seconde laissait survivre un jeton
emis dans la meme seconde que la revocation. Un entier ne souffre d'aucune
granularite.

### CSRF

L'API est authentifiee par jeton porteur, donc immunisee par construction : un
site tiers ne peut pas poser l'en-tete `Authorization`. Seule exception,
`/api/auth/refresh` s'authentifie par cookie. Deux protections s'y cumulent :

- `SameSite=Strict` sur le cookie ;
- **double soumission** : un cookie non-`httpOnly` renvoye en en-tete
  `X-CSRF-Token`. Un site tiers peut declencher la requete, mais la politique
  d'origine du navigateur l'empeche de lire le cookie pour reconstituer
  l'en-tete.

Le cookie de refresh est de plus limite au chemin `/api/auth` : le reste du
site ne le recoit jamais.

### XSS

Trois couches, dont deux suffiraient :

1. **Aucun `innerHTML` dans `frontend/js/`.** Tout le DOM est construit par
   `js/dom.js`, qui pose des noeuds texte. Un pseudo contenant `<script>`
   s'affiche tel quel.
2. **CSP sans `unsafe-inline`** (`nginx.conf`) : meme un echappement oublie
   resterait inerte, aucun script inline ne s'executant.
3. **Normalisation des entrees** (`core/validation.py`) : NFKC, puis
   suppression des caracteres de controle, des espaces de largeur nulle et des
   marques de direction bidirectionnelle — ces derniers permettent d'afficher
   un texte inverse, donc trompeur.

### Injections SQL

Uniquement l'ORM Django, aucun SQL brut nulle part.

### Televersements

Le nom de fichier fourni par le client n'est jamais reutilise (UUID), le type
MIME annonce n'est jamais cru, et l'image est **re-encodee en PNG** : un
fichier polyglotte ne survit pas a l'operation. Un plafond de pixels arrete les
bombes de decompression, et le re-encodage supprime les metadonnees EXIF, qui
contiennent souvent des coordonnees GPS.

### WebSockets

`AllowedHostsOriginValidator` rejette toute poignee de main dont l'`Origin`
n'est pas la notre : sans cela, n'importe quel site pourrait ouvrir une socket
au nom d'un visiteur connecte. Le jeton voyage dans le **premier message
applicatif**, jamais en query string — une URL finit dans les journaux du
reverse proxy et dans l'historique du navigateur.

### Pas de PKCE sur OAuth 42

PKCE protege les clients **publics**, ceux qui ne peuvent pas garder de secret.
Le notre est confidentiel : l'echange du code se fait de serveur a serveur avec
`OAUTH42_SECRET`, qui ne quitte jamais le conteneur. Le parametre `state`,
compare a un cookie ephemere, couvre le risque reel — la fin de parcours forgee
par un tiers.

### Rate limiting

Quota par adresse IP sur connexion, inscription, verification 2FA et
rafraichissement. Argon2 ralentit deja chaque tentative, mais un attaquant
patient finit par passer sur un mot de passe faible : le quota transforme une
attaque de quelques heures en une attaque de plusieurs annees. Redis
indisponible fait basculer sur un compteur en memoire plutot que de bloquer les
connexions.

---

## 5. Frontend

- **Pas d'etape de build.** Des modules ES charges directement par le
  navigateur. Rien a compiler, rien a auditer dans un `node_modules`, et le
  code lu par l'evaluateur est exactement celui qui s'execute.
- **Import dynamique par route** : une page ne telecharge que sa vue.
- **Contrat de nettoyage du routeur** : une vue peut retourner une fonction
  appelee quand on la quitte. C'est ce qui ferme les WebSockets et arrete les
  boucles d'animation — sans quoi quitter une partie laisserait une socket
  ouverte et une `requestAnimationFrame` tournant en fond.
- **Zero erreur en console** : les 4xx sont evites quand ils sont previsibles
  (pas d'appel de rafraichissement sans temoin de session), les promesses
  rejetees sont capturees, et les assets sont servis en `=404` stricts pour
  qu'un chemin de module errone ne recoive jamais `index.html` — ce qui
  provoquerait un avertissement de type MIME.

---

## 6. Infrastructure

- **nginx** termine le TLS, sert le frontend et relaie `/api/` et `/ws/`. Le
  sujet invite a se demander s'il est necessaire : ici oui, puisque HTTPS et
  WSS sont obligatoires et qu'il faut bien servir des fichiers statiques.
- **Certificat auto-signe genere au demarrage du conteneur**, pas au build :
  une cle privee figee dans une couche d'image serait partagee par toute
  personne recuperant l'image.
- **Ports 8080 / 8443** : sur les machines 42, Docker tourne en mode rootless
  et ne peut pas ecouter sur les ports privilegies.
- **Volumes nommes uniquement** dans `docker-compose.yml`, pour la meme raison
  (les bind-mounts avec UID non-root sont interdits). Les bind-mounts de
  developpement sont isoles dans `docker-compose.dev.yml`.
- **PostgreSQL et Redis sur un reseau `internal`** : ni l'hote ni nginx n'ont
  de route vers eux.
- **Le conteneur applicatif ne tourne pas en root** (UID 10001).
- **Pas d'admin Django, pas de sessions Django** : une surface d'attaque en
  moins, et rien dans le sujet ne les demande.

---

## 7. Presence en ligne sans Redis

Un compteur en memoire du process, incremente par socket `ws/live` ouverte.
Un compteur et non un booleen : plusieurs onglets ne doivent pas se marcher
dessus.

Pourquoi pas une cle Redis avec expiration : elle laisserait un utilisateur
« en ligne » plusieurs dizaines de secondes apres la fermeture de son
navigateur. Avec un seul process applicatif, le compteur local est exact et
instantane. `User.last_seen` reste en base pour afficher « vu il y a X ».

---

## 8. RGPD : anonymiser n'est pas supprimer

- **Anonymiser** conserve la ligne du compte et efface tout ce qui identifie la
  personne. Les matchs restent dans l'historique de ses adversaires, sous un
  nom neutre : leurs statistiques ne sont pas faussees.
- **Supprimer** efface la ligne — et il faut alors nettoyer *aussi* les traces
  laissees ailleurs. C'est le point que l'on oublie facilement : les alias
  figes sur les matchs sont des noms lisibles, donc des donnees personnelles.
  Un `ON DELETE SET NULL` seul laisserait « Ada » visible en base apres
  l'effacement de son compte.

Les deux gestes exigent de saisir a nouveau son mot de passe : un onglet laisse
ouvert ne doit pas suffire a effacer un compte.

Le site ne conserve **aucune adresse IP en base** — ni sur les sessions, ni sur
les messages. C'est une donnee personnelle dont le projet n'a aucun usage.
