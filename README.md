# Prospekto

CRM de prospection B2B interne, sans envoi automatique. Cet incrément remplace la persistance applicative SQLite par PostgreSQL, ajoute des migrations versionnées, des profils SMTP chiffrés, CSRF/authentification serveur, suppressions globales et envoi individuel revu avec idempotence durable et état `uncertain` sans retry automatique.

Les connecteurs non validés et Mammouth restent inactifs. Voir `docs/deployment.md` et `docs/sending.md`. Ne pas utiliser de vraies boîtes SMTP en test.
