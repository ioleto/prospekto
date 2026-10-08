# Prospekto
CRM interne de prospection B2B, en français, sans inscription ni envoi automatique.

## État — socle, pas V1
Ce dépôt est un **socle fonctionnel non prêt pour la production**. Il couvre une authentification administrateur, sessions protégées par CSRF, campagnes, prospects, opposition globale et export CSV. Aucun SMTP, envoi réel, connecteur entreprise, collecte automatique, IA Mammouth, détection/fusion avancée ou orchestration V1 n'est activé.

## Authentification et secrets
Le mot de passe administrateur est vérifié avec un hash **Argon2id** dans `ADMIN_PASSWORD_HASH`; aucun mot de passe clair n'est stocké. `ADMIN_PASSWORD_BOOTSTRAP` peut fournir un secret de bootstrap en mémoire au démarrage, mais il n'est jamais persisté : générer puis déployer un hash avec `python -m app.password_hash`, et supprimer le secret de bootstrap. Ne jamais committer `.env`.

## Déploiement Portainer + SWAG (à valider par l'infrastructure)
1. Copier `.env.example` vers `.env`, définir secrets longs et le hash Argon2id.
2. Dans Portainer, déployer `docker-compose.yml` depuis le dépôt Git.
3. Le réseau externe SWAG est configurable par `SWAG_NETWORK` (valeur de référence observée dans le projet : `swag_default`). Le réseau interne PostgreSQL n'expose aucun port hôte.
4. Le vhost de référence `swag/prospekto.subdomain.conf` utilise `prospekto.ioleto.fr`; DNS, certificats et nom réel du réseau restent à confirmer.

Lancement : `docker compose up --build`. Migration : `docker compose exec web python -m app.migrate`. Tests : `python -m unittest discover -s tests -v`.

## Fonctions présentes
- Création réelle de campagnes en base, avec protection CSRF.
- Création de prospects avec provenance documentée.
- Marquage d'opposition global, exclusion du tableau et de l'export CSV.
- Sessions HttpOnly/SameSite, rate-limit rudimentaire, en-têtes de sécurité.

## Production bloquée / limites restantes
Pas de SMTP ni d'envoi réel. Pas de tests PostgreSQL exécutés ici. La compatibilité PostgreSQL de l'application doit encore être implémentée/validée (le code actuel utilise SQLite). La migration, sauvegarde/restauration, secrets Portainer, réseau SWAG, supervision, rotation et revue de conformité doivent être validés. Ne pas présenter ce socle comme prêt production.
