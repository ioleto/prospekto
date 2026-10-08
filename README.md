# Prospekto
CRM de prospection B2B interne, français, sans inscription ni envoi automatique.

## Déploiement Portainer Git + SWAG
Copier `.env.example` vers `.env`, renseigner les secrets hors dépôt, puis Portainer > Stacks > Add stack > Git repository avec `docker-compose.yml`. Le service web rejoint le réseau externe SWAG configurable (`SWAG_NETWORK`, défaut `swag_default`); PostgreSQL reste sur un réseau interne sans port publié. Monter `swag/prospekto.subdomain.conf` dans SWAG. Domaine prévu: `prospekto.ioleto.fr`.

Lancement: `docker compose up --build`. Migration: `docker compose exec web python -m app.migrate`. Tests: `docker compose exec web python -m unittest discover -s tests`.

## Périmètre
Authentification admin sans inscription, session CSRF, rate-limit de connexion, campagnes, prospects avec provenance et consentement, suppression logique prévue par schéma, et connecteurs IA/Mammouth/annuaire désactivés. Aucun envoi, scraping, collecte ou service payant. B2C non activable sans consentement documenté.

Voir `docs/backup-restore.md` et `docs/connectors.md`. Ne jamais committer `.env`.