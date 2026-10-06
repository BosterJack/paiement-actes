# Paiement des demandes d'actes

Service de paiement en ligne des demandes d'actes administratifs (acte de naissance,
casier judiciaire, certificat de résidence) par paiement mobile **MTN, MOOV ou CELTIIS**.

Le service demande un débit à l'opérateur, qui accuse seulement réception. Le résultat
(réussite ou échec) arrive plus tard sous forme de **message signé**. L'opérateur est
simulé dans le projet (`app/simulateur/`, hors périmètre évalué).

**Stack :** Python 3.10+, FastAPI, SQLAlchemy 2, SQLite, interface HTML/JS sans framework
servie par la même application. Une seule commande lance l'API, l'interface et le simulateur.

---

## 1. Installer et démarrer

```bash
git clone <url-du-depot> && cd paiement-actes
python -m venv .venv
# Windows : .venv\Scripts\activate      Linux/macOS : source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8000
```

| Adresse | Contenu |
|---|---|
| http://127.0.0.1:8000 | Interface usager + pupitre du simulateur |
| http://127.0.0.1:8000/docs | Documentation interactive de l'API (Swagger) |

La base SQLite `paiement_actes.db` est créée automatiquement au démarrage.

**Lancer les tests :** `pytest` (49 tests, environ 20 s, sans serveur ni réseau).

### Configuration (variables d'environnement, toutes facultatives)

| Variable | Défaut | Rôle |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./paiement_actes.db` | Base de données (PostgreSQL compatible) |
| `OPERATEUR_SECRET` | `secret-partage-demo` | Secret partagé pour signer / vérifier les résultats |
| `URL_NOTIFICATION` | `http://127.0.0.1:8000/api/operateur/notifications` | Où le simulateur envoie ses résultats (à adapter si vous changez de port) |
| `PAIEMENT_EXPIRATION_SECONDES` | `120` | Délai au-delà duquel un paiement sans résultat expire |
| `SIMULATEUR_DELAI_SECONDES` | `3` | Délai avant l'envoi automatique du résultat |
| `SIMULATEUR_AUTO` | `1` | `0` : le simulateur n'envoie rien tout seul (pilotage manuel uniquement) |

---

## 2. Fonctionnalités

### 2.1 Enregistrer une demande et connaître le montant
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

### 2.2 Lancer le paiement
- Téléphone : **exactement 10 chiffres commençant par `01`** ; opérateur : `MTN`, `MOOV` ou `CELTIIS`.
- Toute donnée invalide est rejetée (422) **avant** tout appel à l'opérateur : aucun débit.
- Réponse **202 Accepted** : le débit est demandé, le paiement est `EN_COURS`.

### 2.3 Un seul débit, quoi qu'il arrive
| Situation | Mécanisme | Résultat |
|---|---|---|
| Demande déjà payée | contrôle du statut + index unique | 409 |
| Paiement déjà en cours | index unique partiel en base | 409 |
| Même requête renvoyée (réseau mobile instable) | en-tête `Idempotency-Key` | 200, **même paiement**, pas de nouveau débit |
| Deux requêtes identiques au même instant | contrainte unique `(usager, Idempotency-Key)` | 1 seul débit |
| Deux requêtes différentes au même instant sur la même demande | index unique partiel « un paiement `EN_COURS` ou `REUSSI` par demande » | 1 seul débit, l'autre reçoit 409 |
| Après un échec | l'échec libère l'index | l'usager peut réessayer |

**Pourquoi en base et pas dans le code :** un test « existe-t-il déjà un paiement ? » suivi
d'une insertion laisse une fenêtre où deux requêtes passent toutes les deux. L'index unique
rend l'opération atomique : la base désigne un seul gagnant. Le paiement est **enregistré
avant l'appel à l'opérateur**, donc seul le gagnant déclenche le débit.

### 2.4 Prise en compte du résultat de l'opérateur
- `POST /api/operateur/notifications`, signature **HMAC-SHA256** du corps brut dans l'en-tête `X-Signature`.
- Signature absente, fausse, ou corps modifié après signature : **401, rien n'est modifié**.
  La comparaison est faite à temps constant (`hmac.compare_digest`).
- Réussite : paiement `REUSSI`, demande `PAYEE`. Échec : paiement `ECHOUE`, la demande reste payable.
- **Un paiement `REUSSI` ou `ECHOUE` ne change plus jamais d'état** : un résultat renvoyé, même
  contradictoire, répond 200 (pour que l'opérateur arrête de réessayer) sans effet.
  Garanti par un `UPDATE … WHERE statut = 'EN_COURS'` : même deux résultats simultanés
  n'en appliquent qu'un.

### 2.5 Paiements dont le résultat n'arrive jamais
- Un paiement `EN_COURS` depuis plus de `PAIEMENT_EXPIRATION_SECONDES` passe à **`EXPIRE`**
  (vérifié à chaque consultation et avant chaque nouveau paiement). L'usager peut réessayer.
- Si le résultat arrive **après** l'expiration, l'état ne change pas, mais le résultat est
  conservé (`resultat_tardif`) et journalisé en erreur pour **rapprochement / remboursement**.

### 2.6 Chacun ne voit que ses données
- Identification simplifiée : `POST /api/usagers` renvoie un jeton opaque, à envoyer en
  `Authorization: Bearer <jeton>`.
- Demandes et paiements d'un autre usager : **404** (on ne révèle pas leur existence).

### 2.7 Suivi par l'usager
- L'interface affiche l'historique des paiements de chaque demande et rafraîchit le statut
  toutes les 2 s jusqu'au résultat.

---

## 3. API

Toutes les routes `/api/demandes*` et `/api/paiements*` exigent `Authorization: Bearer <jeton>`.
Les erreurs ont toujours la forme `{"detail": "..."}`.

| Méthode | Route | Description | Codes |
|---|---|---|---|
| POST | `/api/usagers` | Inscription `{"nom"}` → `{id, nom, jeton}` | 201 |
| GET | `/api/types-actes` | Types d'actes et tarifs | 200 |
| POST | `/api/demandes` | `{"type_acte", "nombre_copies"}` → demande avec `montant` | 201, 401, 422 |
| GET | `/api/demandes` | Mes demandes | 200 |
| GET | `/api/demandes/{id}` | Une demande (statut `EN_ATTENTE_PAIEMENT` / `PAYEE`) | 200, 404 |
| POST | `/api/demandes/{id}/paiements` | `{"telephone", "operateur"}` + en-tête **`Idempotency-Key`** (8 à 100 caractères) | **202** créé, **200** renvoi, 404, 409, 422, 502 |
| GET | `/api/demandes/{id}/paiements` | Historique des paiements d'une demande | 200, 404 |
| GET | `/api/paiements/{id}` | État d'un paiement : `EN_COURS`, `REUSSI`, `ECHOUE`, `EXPIRE` (+ `motif`) | 200, 404 |
| POST | `/api/operateur/notifications` | Résultat signé de l'opérateur (en-tête `X-Signature`) | 200, 401, 404, 422 |
| GET | `/health` | Supervision | 200 |

Format du résultat envoyé par l'opérateur :
```json
{"reference": "…", "id_transaction": "MTN-…", "resultat": "REUSSI", "montant": 3100, "horodatage": "2026-10-06T15:30:00+00:00"}
```

### Exemple complet (curl)
```bash
JETON=$(curl -s -X POST localhost:8000/api/usagers -H 'Content-Type: application/json' -d '{"nom":"Jury"}' | python -c "import sys,json;print(json.load(sys.stdin)['jeton'])")
curl -X POST localhost:8000/api/demandes -H "Authorization: Bearer $JETON" -H 'Content-Type: application/json' \
     -d '{"type_acte":"CASIER_JUDICIAIRE","nombre_copies":2}'              # montant : 3100
curl -X POST localhost:8000/api/demandes/1/paiements -H "Authorization: Bearer $JETON" \
     -H 'Content-Type: application/json' -H 'Idempotency-Key: essai-0001' \
     -d '{"telephone":"0197123456","operateur":"MTN"}'                    # 202 EN_COURS
curl localhost:8000/api/paiements/1 -H "Authorization: Bearer $JETON"   # REUSSI après ~3 s
```

---

## 4. Simulateur d'opérateur : vérifier chaque cas

Le simulateur accuse réception du débit immédiatement, puis envoie le résultat signé.
Tout se pilote depuis l'interface (panneau **Simulateur d'opérateur**, à droite) ou par l'API
`/simulateur` (visible dans `/docs`). La `reference` d'un débit est celle du paiement.

**Mode automatique** (3 s après la demande de débit), selon les 2 derniers chiffres du téléphone :

| Téléphone | Résultat automatique |
|---|---|
| se termine par **00** (ex. `0197000000`) | **Échec** |
| se termine par **99** (ex. `0197000099`) | **Aucune réponse** (pour tester l'expiration ou le pilotage manuel) |
| autre (ex. `0197123456`) | **Réussite** |

**Pas à pas pour le jury :**

| Cas à vérifier | Comment faire | Attendu |
|---|---|---|
| **Réussite** | Payer avec `0197123456` | `REUSSI` après ~3 s, demande `PAYEE` |
| **Échec** | Payer avec `0197000000` | `ECHOUE` ; le bouton Payer redevient disponible |
| **Résultat envoyé deux fois** | Après un résultat, bouton **Renvoyer** (`POST /simulateur/debits/{reference}/renvoyer`) : mêmes octets, même signature | Le service répond 200, l'état ne change pas |
| **Résultat contradictoire** | Après une réussite, bouton **Échec** | 200, le paiement reste `REUSSI` |
| **Signature fausse** | Payer avec `0197000099`, puis bouton **Signature falsifiée** (`POST /simulateur/debits/{reference}/resultat` avec `{"resultat":"REUSSI","signature_valide":false}`) | Le service répond **401**, le paiement reste `EN_COURS` |
| **Résultat qui n'arrive jamais** | Payer avec `0197000099` et attendre 2 min (ou démarrer avec `PAIEMENT_EXPIRATION_SECONDES=20`) | `EXPIRE`, nouvel essai possible |
| **Résultat tardif** | Après l'expiration, bouton **Réussite** | 200, reste `EXPIRE`, `resultat_tardif` conservé et journalisé |
| **Double paiement** | Payer une demande `EN_COURS` ou `PAYEE` | 409, aucun débit supplémentaire (liste du simulateur inchangée) |
| **Téléphone invalide** | `0297123456`, `019712345`, lettres… | 422, aucun débit dans le simulateur |

La colonne **Envois** du pupitre affiche le code HTTP renvoyé par le service à chaque envoi.

---

## 5. Tests automatisés

| Fichier | Ce qui est couvert |
|---|---|
| `tests/test_demandes.py` | calcul du montant (4 cas), montant fourni refusé, copies invalides, authentification, isolation entre usagers |
| `tests/test_lancement_paiement.py` | téléphones invalides (8 cas) sans débit, opérateur inconnu, clé d'idempotence obligatoire, paiement en cours, requête renvoyée = 1 débit, **10 requêtes identiques simultanées = 1 débit**, **10 requêtes différentes simultanées = 1 débit**, opérateur injoignable, isolation |
| `tests/test_notifications.py` | réussite, échec puis nouvel essai, demande payée non repayable, signature fausse / absente, corps modifié après signature, renvoi sans effet, résultat contradictoire ignoré, **2 résultats contradictoires simultanés**, montant incohérent, expiration, résultat tardif |
| `tests/test_simulateur.py` | bout en bout simulateur → service : accusé de réception, réussite, signature falsifiée, renvoi, règles du mode automatique |

Les tests de concurrence lancent de vrais threads synchronisés par une barrière sur une base
SQLite fichier, et vérifient le nombre de débits reçus par un faux opérateur.

---

## 6. Architecture

```
app/
  tarifs.py            grille tarifaire et calcul du montant (source unique)
  models.py            Usager, Demande, Paiement + contraintes d'unicité
  paiements.py         logique métier : lancement, notification, expiration (sans HTTP)
  routes_paiements.py  routes HTTP des paiements et de la notification
  demandes.py          routes usagers / demandes
  signature.py         HMAC-SHA256
  operateur.py         contrat ClientOperateur (interface) + choix de l'implémentation
  securite.py          identification par jeton
  simulateur/          simulateur d'opérateur + pupitre (hors périmètre)
  static/              interface web
tests/
```

Le service ne dépend que de l'interface `ClientOperateur` : remplacer le simulateur par un
vrai client HTTP MTN / MOOV / CELTIIS ne touche pas à la logique métier.

**Cycle de vie d'un paiement :**
```
              résultat REUSSI signé ──► REUSSI   (demande PAYEE, définitif)
EN_COURS ──┤  résultat ECHOUE signé ──► ECHOUE   (définitif, nouvel essai possible)
              délai dépassé         ──► EXPIRE   (nouvel essai possible, résultat tardif conservé)
```

---

## 7. Ce qui fonctionne, ce qui manque et pourquoi

**Fonctionne et testé :** les 4 socles obligatoires et toutes les règles de gestion de l'énoncé
(sections 2 et 5).

**Limites assumées (choix de temps sur l'épreuve) :**

| Manque | Pourquoi / ce que je ferais en production |
|---|---|
| Identification simplifiée (jeton opaque, sans mot de passe) | Autorisée par l'énoncé. En production : authentification de l'État (OIDC / SSO) |
| `create_all` au lieu de migrations | Suffisant pour une démo. En production : Alembic |
| SQLite | Les contraintes utilisées (index unique partiel, UPDATE conditionnel) sont portables sur PostgreSQL, déjà déclarées (`postgresql_where`) ; il suffit de changer `DATABASE_URL` |
| Expiration vérifiée à la consultation, pas par une tâche planifiée | Le statut affiché est toujours juste. En production : tâche périodique, et **interroger l'opérateur sur l'état du débit avant d'expirer** pour éviter un double débit si son résultat est seulement en retard |
| Pas de protection contre le rejeu d'une notification ancienne | Sans effet sur l'état (statuts définitifs), mais en production : rejeter les `horodatage` trop anciens et tracer les `id_transaction` reçus |
| Résultat tardif seulement journalisé | En production : file de rapprochement et remboursement automatique |
| Pas de limitation de débit (rate limiting) ni d'API admin | Hors périmètre de l'épreuve |
| Secret de signature par défaut dans la config | Valeur de démo ; en production, l'application doit refuser de démarrer sans `OPERATEUR_SECRET` |
| Simulateur en mémoire (perdu au redémarrage) | Il est hors périmètre évalué ; les paiements, eux, sont persistés |
