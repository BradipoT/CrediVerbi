# CrediVerbi

Outil de fact-checking : recense des **déclarations** de personnalités publiques (politiques, journalistes, etc.), leur attribue des **verdicts sourcés et gradués**, et calcule des **indices de crédibilité** par personne et par organisation.

Stack : Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL (psycopg), templates Jinja2, tests pytest.

## Principes de conception (garde-fous)

- **On évalue des déclarations, pas des personnes.** Chaque entrée est une citation verbatim avec sa source, sa date et son contexte.
- **Verdicts gradués sur la véracité** : `vrai`, `partiellement_vrai`, `trompeur`, `faux`, `indetermine`. Le qualificatif de « mensonge » n'est pas une catégorie de verdict : il suppose une intention de tromper documentée, qui relève de l'appréciation juridique. Ici, seuls les faits sont notés.
- **Au moins une source obligatoire par verdict**, avec justification écrite.
- **Droit de réponse** : toute personne/organisation concernée peut publier une réponse, affichée à côté du verdict.
- **Journal des corrections** : une correction crée un nouveau verdict qui remplace l'ancien ; l'historique complet reste consultable (append-only).
- **Indice de crédibilité** par personne et par organisation, calculé uniquement à partir des verdicts actifs, avec méthodologie publiée : vrai = 1,0 ; partiellement vrai = 0,5 ; trompeur = 0,25 ; faux = 0 ; indéterminé exclu du calcul.
- **Aucune dimension de genre** : le schéma ne contient délibérément aucun champ genre/sexe, et les indices ne sont jamais ventilés par genre (un test le vérifie).
- **Personnalités publiques uniquement** : une déclaration ne peut être enregistrée que pour une personne marquée `is_public_figure=true`.
- **RGPD** : données minimisées (nom, rôle, organisation), suppression douce (`deleted_at`) via `DELETE /api/persons/{id}`. Avant toute mise en production publique, faire valider la base légale et la politique de conservation par un conseil juridique.
- **Risque juridique** : en France, traiter publiquement quelqu'un de menteur peut relever de la diffamation/injure. D'où des verdicts factuels, sourcés, avec droit de réponse — et une relecture juridique recommandée avant publication ouverte.

## Lancer en local

```bash
docker compose up -d            # PostgreSQL 16 sur localhost:5432
pip install -r requirements.txt
cp .env.example .env            # ajuster si besoin
uvicorn app.main:app --reload   # http://127.0.0.1:8000
```

Sans Docker, `DATABASE_URL` peut pointer vers n'importe quelle instance PostgreSQL, ex. `postgresql+psycopg://user:pass@hote:5432/base`.

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | URL SQLAlchemy (défaut : PostgreSQL local du docker-compose) |
| `CREDIVERBI_TOKEN` | Si renseignée, toutes les écritures (API et formulaires) exigent l'en-tête `Authorization: Bearer <token>` |

## API (préfixe `/api`)

| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | Santé du service |
| POST/GET | `/organizations` | Créer / lister les organisations |
| POST/GET | `/persons`, GET `/persons/{id}` | Créer / lister / détail (avec indice) |
| DELETE | `/persons/{id}` | Suppression douce (RGPD) |
| POST/GET | `/statements` | Créer / lister (`?person_id=`, `?rating=`) |
| GET | `/statements/{id}` | Détail + verdict actif + historique + réponses |
| POST/GET | `/statements/{id}/verdicts` | Verdict (sources obligatoires, `supersedes` pour corriger) / historique |
| POST | `/verdicts/{id}/responses` | Droit de réponse |
| GET | `/index`, `/index/persons/{id}`, `/index/organizations/{id}` | Indices de crédibilité + méthodologie |

L'interface web (server-rendered) reprend les mêmes opérations : `/`, `/statements/{id}`, `/persons/{id}`, `/index`, formulaires `/new/organization`, `/new/person`, `/new/statement`, `/statements/{id}/new/verdict`, `/verdicts/{id}/new/response`.

## Tests

```bash
pytest
```

Par défaut, les tests tournent sur SQLite en mémoire (même schéma SQLAlchemy). Pour les faire tourner contre le PostgreSQL du docker-compose :

```bash
docker compose up -d
DATABASE_URL=postgresql+psycopg://crediverbi:crediverbi@localhost:5432/crediverbi pytest
```

## Structure

```
app/
  config.py      # settings (env)
  db.py          # moteur SQLAlchemy + session
  models.py      # schéma : organization, person, statement, verdict, verdict_source, response
  schemas.py     # validation pydantic des entrées API
  services.py    # calcul des indices de crédibilité + méthodologie
  main.py        # factory FastAPI
  routers/api.py # API JSON
  routers/pages.py # pages HTML (Jinja2)
  templates/     # vues
  static/        # CSS
tests/           # tests API + HTML + garde-fous de schéma
docker-compose.yml
```
