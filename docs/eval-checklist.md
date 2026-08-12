# Checklist d'evaluation

A derouler dans l'ordre. Chaque point se verifie a l'ecran.

## Depart

```
git status
cp .env.example .env
python3 tools/gen_secrets.py .env
docker compose up --build
```

- `.env` n'apparait pas dans `git status`
- Les quatre services passent healthy

Ouvrir https://localhost:8443. Le certificat est auto-signe, l'avertissement du
navigateur est attendu.

- La page d'accueil s'affiche
- http://localhost:8080 redirige vers HTTPS
- La page Diagnostic montre l'API et le WebSocket au vert
- La console du navigateur ne montre aucune erreur

## Application monopage

- Naviguer entre plusieurs pages, puis utiliser Precedent et Suivant
- Recharger une URL profonde comme /play ou /dashboard
- Une URL inexistante affiche la page 404 de l'application

## Partie a deux au clavier

Jouer, puis Partie a deux, meme clavier.

- Le decompte demarre, la balle part
- W et S deplacent la raquette de gauche, les fleches celle de droite
- L'angle de renvoi depend du point d'impact sur la raquette
- Les deux raquettes se deplacent a la meme vitesse
- Le premier au score gagne et le resultat s'affiche

## Tournoi

Jouer, puis Tournoi local, avec cinq alias.

- Le tableau affiche les tours, les rencontres et leur ordre
- Trois joueurs sont exemptes du premier tour
- La prochaine rencontre est annoncee
- Le vainqueur d'un match monte au tour suivant, le perdant est marque elimine
- Le champion est affiche a la fin

## Comptes

- Un mot de passe faible est refuse
- Un pseudo trop court ou un e-mail invalide sont refuses
- Se deconnecter puis se reconnecter
- Un mot de passe errone donne le meme message qu'un compte inexistant
- Televerser un avatar, puis essayer un fichier qui n'est pas une image
- Reprendre un pseudo deja pris est refuse

## Amis et presence

Avec deux comptes dans deux navigateurs.

- Chercher l'autre joueur, l'ajouter, accepter la demande
- L'ami apparait en ligne
- Fermer son onglet le fait passer hors ligne en quelques secondes

## Double authentification

Mon compte, puis Double authentification, puis Activer.

- Le QR code s'affiche, le secret est aussi lisible en clair
- Un code errone est refuse
- Le bon code active la 2FA et affiche dix codes de secours
- A la reconnexion, le mot de passe seul ne suffit plus
- Un code de secours fonctionne, une seule fois
- Desactiver la 2FA demande le mot de passe

## Connexion 42

Sans identifiants dans `.env` :

- Le bouton n'apparait pas
- La route repond 503 et rien d'autre ne casse

Avec identifiants :

- Le bouton mene a l'intra, le retour ouvre la session
- Lier un compte 42 depuis les reglages fonctionne

## Partie a distance

Deux comptes, deux navigateurs.

- Ouvrir une partie, l'autre joueur la voit dans la liste et la rejoint
- La partie demarre seule, chacun voit le nom de l'autre
- Chacun ne controle que sa raquette
- Fermer un onglet affiche un compte a rebours chez l'autre et fige la partie
- Revenir avant la fin reprend la partie par un decompte
- Ne pas revenir donne la victoire par forfait

## Messagerie

- Un message arrive immediatement chez l'autre
- Le pseudo dans la conversation ouvre le profil
- Une invitation arrive avec un bouton pour rejoindre
- Bloquer coupe les messages dans les deux sens
- La conversation disparait de la liste, debloquer la restaure
- Les joueurs attendus recoivent l'annonce du tournoi

## Tableaux de bord

- Bilan, evolution des derniers matchs, face a face par adversaire
- Les chiffres sont lisibles en texte, pas seulement en graphique
- Le detail d'une partie montre le deroule du score point par point

## RGPD

Pied de page, Donnees et vie privee.

- La page explique ce qui est conserve et pourquoi
- L'export produit un JSON complet
- Le fichier ne contient ni mot de passe ni secret 2FA
- Anonymiser demande le mot de passe et remplace le pseudo dans l'historique
- Supprimer demande le mot de passe et efface le compte

## Securite

```
curl -k -i https://localhost:8443/api/me
curl -k -i https://localhost:8443/api/me -H 'Authorization: Bearer a.b.c'
curl -k -i -X POST https://localhost:8443/api/auth/refresh
curl -k -I https://localhost:8443/ | grep -i 'content-security\|strict-transport'
```

- Les trois premieres commandes repondent 401, 401 et 403
- Les en-tetes de securite sont presents
- Un pseudo contenant du HTML s'affiche en toutes lettres
- Une dizaine de connexions ratees finissent par renvoyer 429

## API en ligne de commande

```
curl -sk -X POST https://localhost:8443/api/games \
     -H 'Content-Type: application/json' \
     -d '{"mode":"local","alias1":"Ada","alias2":"Bob"}'
```

Ouvrir la partie dans le navigateur, puis :

```
curl -sk https://localhost:8443/api/games/<id>/state
curl -sk -X POST https://localhost:8443/api/games/<id>/input \
     -H 'Content-Type: application/json' -d '{"side":1,"dir":-1}'
```

- `/state` renvoie l'etat courant
- `/input` deplace la raquette a l'ecran

## Tests

```
make test
```

- La suite passe entierement
