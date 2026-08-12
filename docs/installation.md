# Installation

## Prerequis

Docker avec Compose. Rien d'autre sur la machine hote.

## Lancement

```
cp .env.example .env
python3 tools/gen_secrets.py .env
docker compose up --build
```

Le site repond sur https://localhost:8443. Le certificat est auto-signe :
l'avertissement du navigateur au premier acces est attendu.

Les ports sont superieurs a 1024 parce que Docker tourne en mode rootless sur
les machines de l'ecole et ne peut pas ecouter sur les ports privilegies.

## Services

| Service | Role | Expose |
|---|---|---|
| nginx | TLS, frontend, relais | 8080 et 8443 |
| backend | Application | interne |
| postgres | Base de donnees | interne |
| redis | Etat volatil | interne |

Seul nginx publie des ports. La base et Redis sont sur un reseau interne,
sans route depuis l'hote.

## Raccourcis

```
make          liste les cibles
make up       lance la stack
make down     l'arrete
make test     lance la suite de tests
make fclean   supprime tout, volumes compris
```

## Configuration

Tout passe par `.env`, qui est ignore par git. `.env.example` documente chaque
variable et ne contient aucune valeur reelle.

### Connexion 42

Le module fonctionne sans configuration : le bouton reste masque. Pour
l'activer, creer une application sur
https://profile.intra.42.fr/oauth/applications avec comme redirect URI
`https://localhost:8443/api/auth/oauth42/callback`, puis renseigner
`OAUTH42_UID` et `OAUTH42_SECRET` dans `.env`.

## Developpement

```
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Cette variante monte le code depuis l'hote pour eviter une reconstruction a
chaque modification. Ces montages sont interdits sur les machines de l'ecole,
d'ou leur isolement dans un fichier separe.

## Tests

```
make test
```

La suite couvre la physique du jeu, les tableaux de tournoi, les JWT, le TOTP,
les blocages du chat, les deconnexions en cours de partie et les cascades RGPD.

## Depannage

**Avertissement de securite du navigateur.** Attendu, le certificat est
auto-signe. Parametres avances, puis Continuer vers localhost.

**Port deja utilise.** Changer `HTTP_PORT` et `HTTPS_PORT` dans `.env`.

**HSTS bloque d'autres projets locaux en HTTP.** nginx envoie
`Strict-Transport-Security`, qui s'applique a l'hote localhost tous ports
confondus. Pour l'annuler, ouvrir `chrome://net-internals/#hsts` et supprimer
la politique pour localhost. Pour l'eviter, commenter la ligne correspondante
dans `nginx/nginx.conf`.

**Repartir de zero.**

```
make fclean && make up
```
