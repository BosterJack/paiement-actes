# Paiement des demandes d'actes

Service de paiement en ligne des demandes d'actes administratifs (acte de naissance,
casier judiciaire, certificat de résidence) par paiement mobile **MTN, MOOV ou CELTIIS**.

Le service demande un débit à l'opérateur, qui accuse seulement réception. Le résultat
(réussite ou échec) arrive plus tard sous forme de **message signé**. L'opérateur est
simulé dans le projet (`app/simulateur/`, hors périmètre évalué).

**Dépôt :** https://github.com/BosterJack/paiement-actes

**Stack :** Python 3.10+, FastAPI, SQLAlchemy 2, SQLite ; interface HTML/JS + Bootstrap 5,
servie par la même application. **Une seule commande** lance l'API, l'interface et le simulateur.

**Sommaire :** [1. Démarrer](#1-installer-et-démarrer) · [2. État d'avancement](#2-état-davancement) ·
[3. Fonctionnalités](#3-fonctionnalités) · [4. API](#4-api) · [5. Modèle de données](#5-modèle-de-données) ·
[6. Simulateur : vérifier chaque cas](#6-simulateur-dopérateur--vérifier-chaque-cas) · [7. Tests](#7-tests-automatisés) ·
[8. Architecture du code](#8-architecture-du-code) · [9. Limites](#9-limites-et-suite)

---

## 1. Installer et démarrer

```bash
git clone https://github.com/BosterJack/paiement-actes.git && cd paiement-actes
python -m venv .venv
# Windows : .venv\Scripts\activate      Linux/macOS : source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000
```

| Adresse | Contenu |
|---|---|
| http://127.0.0.1:8000 | Interface usager + console du simulateur (bouton en bas à droite) |
| http://127.0.0.1:8000/docs | Documentation interactive de l'API (Swagger, avec les codes de réponse) |

La base SQLite `paiement_actes.db` est créée automatiquement au démarrage.

**Lancer les tests :** `pytest` (76 tests, environ 30 s, sans serveur ni réseau).

### Configuration (variables d'environnement, toutes facultatives)

| Variable | Défaut | Rôle |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./paiement_actes.db` | Base de données (PostgreSQL compatible) |
| `OPERATEUR_SECRET` | `secret-partage-demo` | Secret partagé pour signer / vérifier les résultats |
| `URL_NOTIFICATION` | `http://127.0.0.1:8000/api/operateur/notifications` | Où le simulateur envoie ses résultats (à adapter si vous changez de port) |
| `PAIEMENT_EXPIRATION_SECONDES` | `120` | Délai au-delà duquel un paiement sans résultat expire |
| `SIMULATEUR_DELAI_SECONDES` | `3` | Délai avant l'envoi automatique du résultat |
| `SIMULATEUR_AUTO` | `1` | `0` : le simulateur n'envoie rien tout seul |

---

## 2. État d'avancement

**Tous les socles obligatoires et toutes les règles de gestion sont implémentés et testés.**
Le fichier [`tests/test_scenario_recette.py`](tests/test_scenario_recette.py) déroule le parcours
complet du jury de bout en bout, avec le vrai simulateur.

| Exigence de l'énoncé | État | Où / comment c'est vérifié |
|---|---|---|
| Enregistrer une demande et indiquer le montant | ✅ | `POST /api/demandes` · `test_demandes.py` |
| Lancer le paiement (téléphone + MTN / MOOV / CELTIIS) | ✅ | `POST /api/demandes/{id}/paiements` · `test_lancement_paiement.py` |
| Simuler l'opérateur : accusé de réception puis résultat signé | ✅ | `app/simulateur/` · `test_simulateur.py` |
| Prendre en compte le résultat, consulter l'état du paiement | ✅ | `POST /api/operateur/notifications`, `GET /api/paiements/{id}` · `test_notifications.py` |
| Montant toujours calculé par le service | ✅ | champ `montant` refusé (422) ; montant de la notification contrôlé |
| Téléphone 10 chiffres commençant par 01, aucun débit si invalide | ✅ | validation avant tout appel à l'opérateur (8 cas testés) |
| Pas de second paiement si payée ou en cours ; nouvel essai après échec | ✅ | index unique partiel en base (409) |
| Même demande envoyée deux fois = un seul débit | ✅ | en-tête `Idempotency-Key` (200, même paiement) |
| Seuls les résultats à signature valide sont pris en compte | ✅ | HMAC-SHA256 sur le corps brut (401 sinon) |
| Un paiement réussi / échoué ne change plus d'état | ✅ | `UPDATE … WHERE statut = 'EN_COURS'` |
| Un seul débit pour deux demandes identiques simultanées | ✅ | contraintes uniques en base · tests à 10 threads synchronisés |
| Tests automatisés des cas critiques | ✅ | 76 tests (section 7) |
| Paiements dont le résultat n'arrive jamais | ✅ | statut `EXPIRE` après délai, nouvel essai possible |
| Un usager n'agit que sur ses propres données | ✅ | comptes NPI / email + mot de passe ; 404 sur les données d'autrui |
| *En plus :* interface web, reconnexion et historique persistant | ✅ | section 3.7 |

Ce qui n'est pas fait et pourquoi : section [9. Limites et suite](#9-limites-et-suite).

---

## 3. Fonctionnalités

### 3.1 Enregistrer une demande et connaître le montant
- L'usager choisit le type d'acte et le nombre de copies (1 à 20).
- **Montant = tarif unitaire × copies + 100 FCFA de frais de service**, calculé par le service
  à partir d'une grille unique (`app/tarifs.py`) :

  | Acte | Tarif unitaire |
  |---|---|
  | Acte de naissance | 1 000 FCFA |
  | Casier judiciaire | 1 500 FCFA |
  | Certificat de résidence | 500 FCFA |

- **Le montant n'est jamais fourni par l'usager** : un champ `montant` envoyé à la création
  de la demande ou au paiement est **refusé (422)**. Le montant du paiement est recopié de
  la demande ; le montant annoncé par l'opérateur dans son résultat est contrôlé.

### 3.2 Lancer le paiement
- Téléphone : **exactement 10 chiffres commençant par `01`** ; opérateur : `MTN`, `MOOV` ou `CELTIIS`.
- Toute donnée invalide est rejetée (422) **avant** tout appel à l'opérateur : aucun débit.
- Réponse **202 Accepted** : le débit est demandé, le paiement est `EN_COURS`.

### 3.3 Un seul débit, quoi qu'il arrive
| Situation | Mécanisme | Résultat |
|---|---|---|
| Demande déjà payée | contrôle du statut + index unique | 409 |
| Paiement déjà en cours | index unique partiel en base | 409 |
| Même requête renvoyée (réseau mobile instable) | en-tête `Idempotency-Key` | 200, **même paiement**, pas de nouveau débit |
| Même clé réutilisée pour une autre demande / un autre numéro | comparaison avec la requête d'origine | 422, aucun débit |
| Deux requêtes identiques au même instant | contrainte unique `(usager, Idempotency-Key)` | 1 seul débit |
| Deux requêtes différentes au même instant sur la même demande | index unique partiel « un paiement `EN_COURS` ou `REUSSI` par demande » | 1 seul débit, l'autre reçoit 409 |
| Après un échec ou une expiration | ces statuts libèrent l'index | l'usager peut réessayer |

**Pourquoi en base et pas dans le code :** un test « existe-t-il déjà un paiement ? » suivi
d'une insertion laisse une fenêtre où deux requêtes passent toutes les deux. L'index unique
rend l'opération atomique : la base désigne un seul gagnant. Le paiement est **enregistré
avant l'appel à l'opérateur**, donc seul le gagnant déclenche le débit.

### 3.4 Prise en compte du résultat de l'opérateur
- `POST /api/operateur/notifications`, signature **HMAC-SHA256** du corps brut dans l'en-tête `X-Signature`.
- Signature absente, fausse, ou corps modifié après signature : **401, rien n'est modifié**.
  La comparaison est faite à temps constant (`hmac.compare_digest`).
- Contrôles de cohérence : le montant et l'identifiant de transaction doivent correspondre à
  ceux du paiement et de l'accusé de réception (422 sinon).
- Réussite : paiement `REUSSI`, demande `PAYEE`. Échec : paiement `ECHOUE`, la demande reste payable.
- **Un paiement `REUSSI` ou `ECHOUE` ne change plus jamais d'état** : un résultat renvoyé, même
  contradictoire, répond 200 (pour que l'opérateur arrête de réessayer) sans effet.
  Garanti par un `UPDATE … WHERE statut = 'EN_COURS'` : même deux résultats simultanés
  n'en appliquent qu'un.

### 3.5 Paiements dont le résultat n'arrive jamais
- Un paiement `EN_COURS` depuis plus de `PAIEMENT_EXPIRATION_SECONDES` passe à **`EXPIRE`**
  (vérifié à chaque consultation, avant chaque nouveau paiement et à la réception d'un résultat).
  L'usager peut réessayer.
- Si le résultat arrive **après** l'expiration, l'état ne change pas, mais le résultat est
  conservé (`resultat_tardif`) et journalisé en erreur pour **rapprochement / remboursement**.

### 3.6 Comptes usagers : chacun ne voit que ses données
- **Inscription** : nom, **NPI** (10 chiffres), email, mot de passe (8 caractères minimum).
  NPI et email sont uniques (409 sinon).
- **Connexion par NPI ou par email** + mot de passe : l'usager retrouve à tout moment, depuis
  n'importe quel appareil, ses demandes et l'historique de ses paiements.
- Mots de passe **hachés avec scrypt** (sel aléatoire, comparaison à temps constant).
- Connexion refusée : **même message et même temps de calcul** que le compte existe ou non,
  pour ne pas révéler quels NPI / emails sont inscrits.
- Demandes et paiements d'un autre usager : **404** (on ne révèle pas leur existence).

### 3.7 Interface web
- Page d'accueil avec connexion / création de compte, tableau de bord avec indicateurs,
  demandes et statuts mis à jour en direct.
- Fenêtre de paiement : choix de l'opérateur par son logo (MTN MoMo, Moov Money, Celtiis Cash).
- **Saisie guidée du numéro** : indicatif 🇧🇯 +229, chiffres uniquement, espacement automatique
  (`01 97 12 34 56`), 10 chiffres au maximum, alerte immédiate si le numéro ne commence pas par `01`,
  bouton **Payer** désactivé tant que le numéro n'est pas valide. Le serveur revalide de toute façon.
- Suivi du paiement en temps réel et historique des tentatives.
- Une clé d'idempotence par clic sur « Payer », réutilisée si le réseau coupe.

*Logos des opérateurs : marques de leurs propriétaires respectifs, utilisés uniquement pour
identifier le moyen de paiement (MTN : Wikimedia Commons ; Moov Africa : Wikipédia ; Celtiis : celtiis.bj).*

---

## 4. API

**Conventions**
- Ressources REST en français ; un paiement est une sous-ressource de sa demande
  (`/api/demandes/{id}/paiements`), consultable aussi directement (`/api/paiements/{id}`).
- Identification : `Authorization: Bearer <jeton>` (obtenu à l'inscription ou à la connexion),
  obligatoire sur toutes les routes `/api/demandes*`, `/api/paiements*` et `/api/usagers/moi`.
- Erreurs : toujours `{"detail": "..."}`. Montants en FCFA entiers.

| Méthode | Route | Description | Codes |
|---|---|---|---|
| POST | `/api/usagers` | Inscription `{"nom", "npi", "email", "mot_de_passe"}` → `{id, nom, jeton}` | 201, 409, 422 |
| POST | `/api/sessions` | Connexion `{"identifiant": NPI ou email, "mot_de_passe"}` → `{id, nom, jeton}` | 200, 401 |
| GET | `/api/usagers/moi` | Profil de l'usager connecté | 200, 401 |
| GET | `/api/types-actes` | Types d'actes et tarifs | 200 |
| POST | `/api/demandes` | `{"type_acte", "nombre_copies"}` → demande avec `montant` | 201, 401, 422 |
| GET | `/api/demandes` | Mes demandes | 200 |
| GET | `/api/demandes/{id}` | Une demande (statut `EN_ATTENTE_PAIEMENT` / `PAYEE`) | 200, 404 |
| POST | `/api/demandes/{id}/paiements` | `{"telephone", "operateur"}` + en-tête **`Idempotency-Key`** (8 à 100 caractères) | **202** créé, **200** renvoi, 404, 409, 422, 502 |
| GET | `/api/demandes/{id}/paiements` | Historique des tentatives de paiement | 200, 404 |
| GET | `/api/paiements/{id}` | État : `EN_COURS`, `REUSSI`, `ECHOUE`, `EXPIRE` (+ `motif`) | 200, 404 |
| POST | `/api/operateur/notifications` | Résultat signé de l'opérateur (en-tête `X-Signature`) | 200, 401, 404, 422 |
| GET | `/health` | Supervision | 200 |

**Codes d'erreur**

| Code | Signification |
|---|---|
| 401 | Jeton absent / invalide, identifiants incorrects, ou signature de l'opérateur invalide |
| 404 | Ressource inexistante **ou appartenant à un autre usager** |
| 409 | Conflit avec une règle de gestion : demande déjà payée, paiement en cours, compte existant |
| 422 | Donnée invalide (téléphone, opérateur, NPI, montant fourni, clé d'idempotence réutilisée, notification incohérente) |
| 500 | Erreur inattendue : journalisée côté serveur, aucun détail technique renvoyé |
| 502 | Opérateur injoignable : le paiement passe à `ECHOUE`, l'usager peut réessayer |

Format du résultat envoyé par l'opérateur :
```json
{"reference": "…", "id_transaction": "MTN-…", "resultat": "REUSSI", "montant": 3100, "horodatage": "2026-10-06T15:30:00+00:00"}
```

### Exemple complet (curl)
```bash
curl -X POST localhost:8000/api/usagers -H 'Content-Type: application/json' \
     -d '{"nom":"Jury ASIN","npi":"1234567890","email":"jury@exemple.bj","mot_de_passe":"motdepasse1"}'
JETON=$(curl -s -X POST localhost:8000/api/sessions -H 'Content-Type: application/json' \
     -d '{"identifiant":"1234567890","mot_de_passe":"motdepasse1"}' | python -c "import sys,json;print(json.load(sys.stdin)['jeton'])")
curl -X POST localhost:8000/api/demandes -H "Authorization: Bearer $JETON" -H 'Content-Type: application/json' \
     -d '{"type_acte":"CASIER_JUDICIAIRE","nombre_copies":2}'              # montant : 3100
curl -X POST localhost:8000/api/demandes/1/paiements -H "Authorization: Bearer $JETON" \
     -H 'Content-Type: application/json' -H 'Idempotency-Key: essai-0001' \
     -d '{"telephone":"0197123456","operateur":"MTN"}'                    # 202 EN_COURS
curl localhost:8000/api/paiements/1 -H "Authorization: Bearer $JETON"   # REUSSI après ~3 s
```

---

## 5. Modèle de données

```
usagers 1 ──── n demandes 1 ──── n paiements
```

| Table | Champs principaux | Contraintes (garanties par la base) |
|---|---|---|
| `usagers` | `nom`, `npi`, `email`, `mot_de_passe_hache`, `jeton` | `npi`, `email`, `jeton` uniques |
| `demandes` | `usager_id`, `type_acte`, `nombre_copies`, `montant`, `statut` | copies entre 1 et 20, `montant > 0`, statut ∈ {`EN_ATTENTE_PAIEMENT`, `PAYEE`} |
| `paiements` | `reference`, `demande_id`, `usager_id`, `cle_idempotence`, `operateur`, `telephone`, `montant`, `statut`, `id_transaction_operateur`, `motif`, `resultat_tardif` | `reference` unique ; **unique (`usager_id`, `cle_idempotence`)** ; **unique partiel (`demande_id`) quand statut ∈ {`EN_COURS`, `REUSSI`}** ; statut ∈ {`EN_COURS`, `REUSSI`, `ECHOUE`, `EXPIRE`} ; opérateur ∈ {`MTN`, `MOOV`, `CELTIIS`} ; `montant > 0` |

**Choix de conception**
- **Un paiement = une tentative.** Une demande garde l'historique de toutes ses tentatives
  (échouées, expirées) ; au plus une est active à un instant donné.
- Le **montant est copié** de la demande dans le paiement : c'est la trace de ce qui a été débité.
- La **`reference`** (générée par le service) est transmise à l'opérateur, qui la renvoie
  dans son résultat ; l'opérateur ne voit jamais nos identifiants internes.
- Index `(statut, cree_le)` pour retrouver efficacement les paiements à expirer.

**Cycle de vie d'un paiement :**
```
              résultat REUSSI signé ──► REUSSI   (demande PAYEE, définitif)
EN_COURS ──┤  résultat ECHOUE signé ──► ECHOUE   (définitif, nouvel essai possible)
              délai dépassé         ──► EXPIRE   (nouvel essai possible, résultat tardif conservé)
```

---

## 6. Simulateur d'opérateur : vérifier chaque cas

Le simulateur accuse réception du débit immédiatement, puis envoie le résultat signé.
Il se pilote depuis la **console opérateur** (bouton noir « Simulateur opérateur » en bas à
droite de l'interface) ou par l'API `/simulateur` (visible dans `/docs`).

**Choisir la réponse de l'opérateur, avant de payer** : sélecteur en haut de la console
(`PUT /simulateur/mode`). La réponse arrive environ 3 s après la demande de débit.

| Mode | Réponse automatique |
|---|---|
| **Selon le numéro** (par défaut) | numéro en **…00** → échec · en **…99** → aucune réponse · sinon → réussite |
| **Toujours réussite** | réussite, quel que soit le numéro |
| **Toujours échec** | échec, quel que soit le numéro |
| **Manuel** | aucune réponse : le jury choisit avec les boutons de la console |

> Un résultat déjà reçu est **définitif** : cliquer ensuite sur « Échec » après une réussite
> ne change rien. C'est justement une règle de gestion à vérifier.

**Pas à pas pour le jury** (après avoir créé un compte depuis la page d'accueil) :

| Cas à vérifier | Comment faire | Attendu |
|---|---|---|
| **Réussite** | Mode « Toujours réussite », puis payer | `REUSSI` après ~3 s, demande `PAYEE` |
| **Échec** | Mode « Toujours échec », puis payer | `ECHOUE` ; le formulaire réapparaît pour réessayer |
| **Résultat envoyé deux fois** | Après un résultat, bouton **Renvoyer** : mêmes octets, même signature | Le service répond 200, l'état ne change pas |
| **Résultat contradictoire** | Après une réussite, bouton **Échec** | 200, le paiement reste `REUSSI` |
| **Signature fausse** | Mode « Manuel », payer, puis bouton **Signature falsifiée** | Le service répond **401**, le paiement reste `EN_COURS` |
| **Résultat qui n'arrive jamais** | Mode « Manuel », payer et attendre 2 min (ou démarrer avec `PAIEMENT_EXPIRATION_SECONDES=20`) | `EXPIRE`, nouvel essai possible |
| **Résultat tardif** | Après l'expiration, bouton **Réussite** | 200, reste `EXPIRE`, `resultat_tardif` conservé et journalisé |
| **Double paiement** | Payer une demande `EN_COURS` ou `PAYEE` (via `/docs`) | 409, aucun débit supplémentaire dans la console |
| **Téléphone invalide** | `0297123456`, `019712345`, lettres… (via `/docs`) | 422, aucun débit dans la console |

La console affiche, pour chaque envoi, le code HTTP renvoyé par le service.

---

## 7. Tests automatisés

| Fichier | Ce qui est couvert |
|---|---|
| `test_scenario_recette.py` | **parcours complet du jury**, de la demande à la reconnexion, avec le vrai simulateur |
| `test_demandes.py` | calcul du montant (4 cas), montant fourni refusé, copies invalides, authentification, isolation |
| `test_lancement_paiement.py` | téléphones invalides (8 cas) sans débit, opérateur inconnu, clé obligatoire, paiement en cours, renvoi = 1 débit, clé réutilisée (2 cas), **10 requêtes identiques simultanées = 1 débit**, **10 requêtes différentes simultanées = 1 débit**, opérateur injoignable, isolation |
| `test_notifications.py` | réussite, échec puis nouvel essai, demande payée non repayable, signature fausse / absente, corps modifié après signature, renvoi sans effet, résultat contradictoire ignoré, **2 résultats contradictoires simultanés**, montant ou transaction incohérents, expiration, résultat tardif |
| `test_comptes.py` | reconnexion par NPI ou email, refus avec message identique, doublons, champs invalides (6 cas), mot de passe haché |
| `test_simulateur.py` | bout en bout simulateur → service, modes de réponse |
| `test_robustesse.py` | contraintes refusées par la base (6 cas), erreur inattendue → 500 sans fuite d'information |

Les tests de concurrence lancent de vrais threads synchronisés par une barrière sur une base
SQLite fichier, et comptent les débits reçus par l'opérateur.

---

## 8. Architecture du code

```
app/
  main.py              assemblage de l'application
  routes/              couche HTTP, volontairement mince : validation, identification, codes HTTP
    comptes.py  demandes.py  paiements.py  operateur.py (notifications)
  services/            règles de gestion, sans dépendance à HTTP (testables directement)
    comptes.py  demandes.py  paiements.py
  models.py            tables et contraintes
  schemas.py           contrats d'entrée / sortie de l'API (Pydantic)
  erreurs.py           ErreurMetier + format d'erreur unique + erreurs inattendues (500)
  tarifs.py            grille tarifaire et calcul du montant (source unique)
  operateur.py         contrat ClientOperateur (interface) + choix de l'implémentation
  signature.py         HMAC-SHA256        mots_de_passe.py  hachage scrypt
  securite.py          identification de l'usager par jeton
  simulateur/          simulateur d'opérateur + console (hors périmètre)
  static/              interface web
tests/
```

- Les services lèvent des `ErreurMetier(code, message)` ; un gestionnaire unique les traduit en
  réponse HTTP `{"detail": ...}`. Toute autre exception est journalisée et renvoyée en 500.
- Le service ne dépend que de l'interface `ClientOperateur` : remplacer le simulateur par un
  vrai client HTTP MTN / MOOV / CELTIIS ne touche pas à la logique métier.
- Journalisation des événements de paiement (débit demandé, signature rejetée, résultat ignoré,
  incohérence, expiration, résultat tardif).

---

## 9. Limites et suite

| Manque | Pourquoi / ce que je ferais en production |
|---|---|
| NPI non vérifié auprès du registre national, email non confirmé | Vérification auprès du référentiel d'identité ou connexion via le fournisseur d'identité de l'État (OIDC) ; email de confirmation |
| Jeton de session sans expiration ni révocation | Jeton à durée limitée (JWT court + refresh) et déconnexion côté serveur |
| Pas de limitation des tentatives de connexion ni de débit (rate limiting) | Limitation par IP / compte et verrouillage temporaire |
| `create_all` au lieu de migrations | Alembic |
| SQLite | Les contraintes utilisées (index unique partiel, CHECK, UPDATE conditionnel) sont portables sur PostgreSQL et déjà déclarées (`postgresql_where`) : il suffit de changer `DATABASE_URL` |
| Expiration vérifiée à la lecture, pas par une tâche planifiée | Le statut affiché est toujours juste. En production : tâche périodique, et **interroger l'opérateur sur l'état du débit avant d'expirer**, pour éviter un double débit si son résultat est seulement en retard |
| Opérateur injoignable → paiement `ECHOUE` | Si la demande de débit a pu être reçue malgré l'erreur réseau, il faudrait interroger l'opérateur avant d'autoriser un nouvel essai |
| Pas de protection contre le rejeu d'une notification ancienne | Sans effet sur l'état (statuts définitifs) ; en production, rejeter les `horodatage` trop anciens |
| Résultat tardif seulement journalisé | File de rapprochement et remboursement automatique |
| Secret de signature par défaut dans la config | Valeur de démo ; en production, refuser de démarrer sans `OPERATEUR_SECRET` |
| Simulateur en mémoire (perdu au redémarrage) | Hors périmètre évalué ; les paiements, eux, sont persistés |
| Interface dépendante d'un CDN (Bootstrap) | Sans Internet, l'interface fonctionne mais sans mise en forme ; en production, embarquer les fichiers |
