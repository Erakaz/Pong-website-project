# Choix techniques

Le sujet demande que chaque choix soit justifiable. Ce document donne la raison
de ceux qui ne vont pas de soi.

## Dependances

Le projet en utilise neuf.

| Dependance | Role |
|---|---|
| Django | Impose par le module Framework |
| Channels, Daphne | WebSocket et serveur ASGI |
| channels-redis | Echange de messages entre les connexions |
| psycopg | Pilote PostgreSQL, impose par le module Database |
| argon2-cffi | Hachage des mots de passe |
| Pillow | Re-encodage des avatars |
| redis | Compteurs de limitation de debit |
| Bootstrap | Impose par le module front-end toolkit |
| qrcode-generator | Calcul de la matrice d'un QR code |

Quatre bibliotheques courantes sont ecartees.

Django REST Framework n'appartient pas a Django officiel. Les vues JSON et la
validation sont ecrites a la main dans `core/http.py` et `core/validation.py`.

PyJWT et pyotp sont ecartees parce qu'emettre un JWT et verifier un code TOTP
sont l'objet meme du module 2FA. Les deux sont implementes dans
`accounts/jwt_utils.py` et `accounts/totp.py`.

django-allauth resoudrait a elle seule le module d'authentification 42, ce que
le sujet interdit. Le flux OAuth est ecrit avec `urllib` dans
`accounts/oauth42.py`.

## Le jeu

La physique tourne sur le serveur, dans `game/engine.py`. Le client envoie une
direction parmi trois et affiche les instantanes recus. Il ne calcule rien.

Un client modifie n'a donc aucune position a falsifier, et la vitesse de
raquette est une constante unique partagee par les deux joueurs.

Le moteur simule 60 fois par seconde et diffuse 30 fois par seconde. Le client
affiche l'etat tel qu'il etait 100 ms plus tot, en interpolant entre deux
instantanes recus. Sans ce retard il faudrait extrapoler, et la balle sauterait
a chaque correction. Sa propre raquette est en revanche predite localement,
sinon une touche ne se verrait qu'apres un aller-retour reseau.

A pleine vitesse la balle parcourt environ 14 unites par pas de temps, pour un
rayon de 8. Le deplacement est donc decoupe en sous-pas, sans quoi elle
traverserait une raquette. Un test fait suivre la balle par les deux raquettes
pendant 60 secondes et verifie qu'aucun but n'est marque.

L'etat des parties en cours vit en memoire du processus. Le projet lance un
seul conteneur applicatif. Passer a plusieurs demanderait de deplacer la boucle
de jeu dans un processus dedie.

Une deconnexion met la partie en pause. Le joueur absent a 20 secondes pour
revenir, au-dela la partie est perdue par forfait. La reprise passe toujours
par un decompte.

## Identite et doublons

Le sujet demande de justifier ce point.

L'e-mail est unique et sert d'identifiant de connexion. Le pseudo est unique
separement : c'est le nom affiche dans les tournois et le chat, et deux
homonymes rendraient un tableau illisible. Un tournoi impose des alias
distincts pour la meme raison.

Un compte anonymise libere son pseudo et perd son e-mail. Le champ accepte donc
la valeur nulle, que PostgreSQL autorise plusieurs fois dans un index unique.

Si l'e-mail renvoye par l'intra 42 correspond deja a un compte cree par mot de
passe, la connexion 42 est refusee. L'utilisateur doit se connecter normalement
puis lier son compte depuis ses reglages. Lier automatiquement donnerait le
compte a quiconque controle l'adresse e-mail.

## Sessions

Deux jetons cohabitent.

| | Access token | Refresh token |
|---|---|---|
| Nature | JWT signe HS256 | Chaine aleatoire |
| Duree | 15 minutes | 14 jours |
| Transport | En-tete Authorization | Cookie httpOnly |
| Cote client | Memoire JavaScript | Cookie, illisible par le JS |
| Cote serveur | Rien | SHA-256 uniquement |

L'access token n'est jamais ecrit dans localStorage, qui est lisible par
n'importe quel script de la page. Le refresh token n'est stocke que sous forme
d'empreinte, comme un mot de passe.

Chaque rafraichissement invalide l'ancien jeton. Si un jeton deja consomme est
represente, la session entiere est revoquee.

La revocation globale passe par un numero de generation sur le compte plutot
que par une date. Comparer un horodatage a la seconde laissait survivre un
jeton emis dans la meme seconde que la revocation.

## Securite

L'API s'authentifie par jeton porteur, ce qui la rend insensible au CSRF. La
seule exception est la route de rafraichissement, authentifiee par cookie.
Elle est protegee par `SameSite=Strict` et une double soumission : un cookie
lisible par le JavaScript, renvoye en en-tete, qu'un site tiers ne peut pas
lire.

Trois couches traitent les injections de script. Le DOM est construit sans
`innerHTML`, par les helpers de `js/dom.js`. La politique de securite du
contenu interdit tout script inline. Les entrees sont normalisees en NFKC et
debarrassees des caracteres de controle et des marques de direction, qui
permettent d'afficher un texte trompeur.

Les requetes passent uniquement par l'ORM Django.

Un avatar televerse n'est jamais stocke tel quel. Son nom est remplace par un
identifiant aleatoire, le type declare par le navigateur est ignore, et l'image
est re-encodee en PNG. Un fichier qui serait a la fois une image valide et du
code executable ne survit pas a l'operation, et les metadonnees EXIF, qui
contiennent souvent des coordonnees GPS, disparaissent.

Les WebSockets refusent toute connexion dont l'en-tete Origin n'est pas celui du
site. Le jeton voyage dans le premier message applicatif, jamais dans l'URL, qui
finirait dans les journaux du proxy.

PKCE n'est pas utilise pour OAuth 42. Il protege les clients incapables de
garder un secret, ce qui n'est pas le cas ici : l'echange se fait de serveur a
serveur. Le parametre `state`, compare a un cookie ephemere, couvre le risque
reel.

Les routes de connexion, d'inscription, de verification 2FA et de
rafraichissement sont limitees par adresse IP.

## Frontend

Le frontend n'a pas d'etape de construction. Ce sont des modules ES charges
directement par le navigateur, importes route par route.

Une vue peut retourner une fonction de nettoyage, que le routeur appelle quand
on la quitte. C'est ce qui ferme les WebSockets et arrete les boucles
d'animation.

La console doit rester vide. Les reponses 4xx previsibles sont evitees, les
promesses rejetees sont capturees, et les fichiers statiques sont servis en 404
strict pour qu'un chemin de module errone ne recoive pas la page HTML.

## Infrastructure

nginx termine le TLS, sert le frontend et relaie les appels applicatifs. Le
certificat auto-signe est genere au demarrage du conteneur, pas a la
construction de l'image, pour qu'une cle privee ne soit pas figee dans une
couche partagee.

Les ports 8080 et 8443 sont choisis parce que Docker tourne en mode rootless
sur les machines de l'ecole et ne peut pas ecouter sur les ports privilegies.
Pour la meme raison, le fichier de composition n'utilise que des volumes
nommes ; les montages de developpement sont dans un fichier separe.

PostgreSQL et Redis sont sur un reseau interne, sans route depuis l'exterieur.
Le conteneur applicatif ne tourne pas en root.

L'administration Django et les sessions Django ne sont pas installees.

## Presence en ligne

Un compteur en memoire, incremente par connexion ouverte. Un compteur et non un
booleen, car un utilisateur peut avoir plusieurs onglets.

Une cle Redis avec expiration laisserait quelqu'un affiche en ligne plusieurs
dizaines de secondes apres la fermeture de son navigateur. Avec un seul
processus applicatif, le compteur local est exact.

## RGPD

Anonymiser conserve la ligne du compte et efface ce qui identifie la personne.
Les matchs restent dans l'historique des adversaires sous un nom neutre, ce qui
laisse leurs statistiques justes.

Supprimer efface la ligne. Il faut alors nettoyer aussi les traces laissees
ailleurs : les alias figes sur les matchs sont des noms lisibles, donc des
donnees personnelles. Une simple cle etrangere mise a nul les laisserait
visibles.

Les deux operations demandent le mot de passe.

Aucune adresse IP n'est conservee en base.
