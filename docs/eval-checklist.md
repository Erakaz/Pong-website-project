# Checklist d'evaluation

A derouler dans l'ordre. Chaque etape se verifie a l'ecran, sans lire de code.

---

## 0. Depart a froid

```bash
git status                  # .env ne doit PAS apparaitre
cp .env.example .env
python3 tools/gen_secrets.py .env
docker compose up --build
```

- [ ] Les quatre services demarrent et passent `healthy` (`docker compose ps`)
- [ ] Aucun secret n'est suivi par git

---

## 1. Le site repond

Ouvrir **<https://localhost:8443>** (avertissement de certificat attendu :
il est auto-signe).

- [ ] La page d'accueil s'affiche
- [ ] `http://localhost:8080` redirige vers HTTPS
- [ ] Page **Diagnostic** : API et WebSocket au vert, transport HTTPS
- [ ] Console du navigateur : **aucune erreur, aucun avertissement**

---

## 2. Application monopage

- [ ] Naviguer entre plusieurs pages, puis utiliser **Precedent** et
      **Suivant** du navigateur : la bonne page s'affiche a chaque fois
- [ ] Recharger directement une URL profonde (`/play`, `/dashboard`) :
      elle s'affiche, pas de 404
- [ ] Une URL inexistante affiche la page 404 de l'application

---

## 3. Partie obligatoire — Pong a deux sur un clavier

*Jouer* → *Partie a deux, meme clavier* → *Lancer la partie*.

- [ ] Le decompte demarre, la balle part
- [ ] **W / S** deplacent la raquette de gauche, **↑ / ↓** celle de droite
- [ ] La balle rebondit sur les murs et sur les raquettes, l'angle depend du
      point d'impact
- [ ] Les deux raquettes se deplacent exactement a la meme vitesse
- [ ] Le premier au score cible gagne, le resultat s'affiche

---

## 4. Partie obligatoire — Tournoi

*Jouer* → *Tournoi local*. Saisir 5 alias (pour voir les exemptions).

- [ ] Le tableau complet s'affiche : tours, rencontres, ordre
- [ ] Trois joueurs sont exemptes du premier tour, un seul match s'y joue
- [ ] Le bandeau annonce clairement la **prochaine rencontre**
- [ ] Jouer ce match : le vainqueur monte en demi-finale, le perdant est
      marque « elimine »
- [ ] Aller au bout : le champion est affiche

---

## 5. Comptes

- [ ] Creer un compte : un mot de passe faible est refuse avec un message clair
- [ ] Un pseudo trop court, un e-mail invalide : refuses
- [ ] Se deconnecter, se reconnecter
- [ ] Mot de passe errone : message identique a celui d'un compte inexistant
      (l'API ne dit pas qui est inscrit)
- [ ] Televerser un avatar ; essayer un fichier qui n'est pas une image :
      refuse
- [ ] Modifier son pseudo ; en reprendre un deja pris : refuse

---

## 6. Amis et presence

Avec deux comptes, dans deux navigateurs.

- [ ] Chercher l'autre joueur, l'ajouter en ami, accepter la demande
- [ ] L'ami apparait **en ligne**
- [ ] Fermer l'onglet de l'ami : il passe **hors ligne** en quelques secondes,
      sans rechargement de page

---

## 7. Double authentification

*Mon compte* → *Double authentification* → *Activer*.

- [ ] Le QR code s'affiche, le secret est aussi lisible en clair
- [ ] Scanner avec une vraie application d'authentification
- [ ] Un code errone est refuse
- [ ] Le bon code active la 2FA et affiche **10 codes de secours**
- [ ] Se deconnecter, se reconnecter : le mot de passe seul ne suffit plus
- [ ] Le code de l'application ouvre la session
- [ ] Recommencer avec un **code de secours** : il fonctionne, une seule fois
- [ ] Desactiver la 2FA : le mot de passe est exige

---

## 8. Connexion 42

Sans credentials dans `.env` :

- [ ] Le bouton « Se connecter avec 42 » **n'apparait pas**
- [ ] `https://localhost:8443/api/auth/oauth42/login` repond 503 avec un
      message clair, et rien d'autre ne casse

Avec credentials :

- [ ] Le bouton apparait et mene a l'intra 42
- [ ] Le retour cree la session et redirige vers l'accueil
- [ ] Depuis *Mon compte*, lier un compte 42 a un compte existant fonctionne

---

## 9. Partie a distance

Deux comptes, deux navigateurs.

- [ ] *En ligne* → *Ouvrir une partie* : ecran d'attente
- [ ] L'autre joueur voit la partie dans la liste et la rejoint
- [ ] La partie demarre toute seule, chacun voit le nom de l'autre
- [ ] Chacun ne controle **que sa propre raquette**
- [ ] Fermer l'onglet d'un joueur : l'autre voit « adversaire deconnecte » avec
      un compte a rebours, la partie se fige
- [ ] Revenir avant la fin du compte a rebours : la partie reprend par un
      decompte
- [ ] Ne pas revenir : forfait, victoire enregistree pour celui qui est reste

---

## 10. Messagerie

- [ ] Envoyer un message : il arrive **instantanement** chez l'autre
- [ ] Cliquer sur le pseudo depuis la conversation ouvre le profil
- [ ] *Inviter a jouer* : l'invitation arrive avec un bouton pour rejoindre
- [ ] **Bloquer** : plus aucun message ne passe, dans les deux sens
- [ ] La conversation disparait de la liste
- [ ] Debloquer la restaure
- [ ] Lors d'un tournoi a distance, les deux joueurs attendus recoivent une
      annonce du systeme

---

## 11. Tableaux de bord

- [ ] *Stats* : bilan, evolution des derniers matchs, face a face par
      adversaire
- [ ] Les chiffres sont aussi lisibles en texte, pas seulement dans les
      graphiques
- [ ] *Detail* d'une partie : deroule du score point par point, duree, plus
      long echange

---

## 12. RGPD

Pied de page → *Donnees et vie privee*.

- [ ] La page explique ce qui est conserve, pourquoi, et pour combien de temps
- [ ] *Telecharger toutes mes donnees* produit un JSON complet
- [ ] Le fichier ne contient **ni mot de passe, ni secret 2FA**
- [ ] *Anonymiser* exige le mot de passe ; apres coup, le pseudo a disparu de
      l'historique des adversaires, remplace par un nom neutre
- [ ] *Supprimer* exige le mot de passe et efface le compte

---

## 13. Securite

```bash
# Route protegee sans jeton
curl -k -i https://localhost:8443/api/me                       # 401

# Jeton falsifie
curl -k -i https://localhost:8443/api/me -H 'Authorization: Bearer a.b.c'   # 401

# Rafraichissement sans en-tete anti-CSRF
curl -k -i -X POST https://localhost:8443/api/auth/refresh     # 403

# En-tetes de securite
curl -k -I https://localhost:8443/ | grep -iE 'content-security|strict-transport|x-content-type'
```

- [ ] Un pseudo contenant `<script>alert(1)</script>` s'affiche **en toutes
      lettres**, aucun script ne s'execute
- [ ] Une dizaine de tentatives de connexion ratees d'affilee finissent par
      renvoyer 429

---

## 14. API en ligne de commande

Exigence du module *Server-Side Pong*.

```bash
ID=$(curl -sk -X POST https://localhost:8443/api/games \
      -H 'Content-Type: application/json' \
      -d '{"mode":"local","alias1":"Ada","alias2":"Bob"}' | grep -o '"id":"[^"]*' | cut -d'"' -f4)

# Ouvrir https://localhost:8443/game/$ID dans le navigateur, puis :
curl -sk https://localhost:8443/api/games/$ID/state
curl -sk -X POST https://localhost:8443/api/games/$ID/input \
     -H 'Content-Type: application/json' -d '{"side":1,"dir":-1}'
```

- [ ] `/state` renvoie l'etat courant de la partie
- [ ] `/input` deplace bien la raquette a l'ecran

---

## 15. Tests

```bash
make test
```

- [ ] La suite passe entierement
- [ ] Elle couvre notamment : la physique du jeu, les tableaux de tournoi,
      les JWT, le TOTP (vecteurs officiels de la RFC 6238), les blocages du
      chat, les deconnexions en cours de partie et les cascades RGPD
