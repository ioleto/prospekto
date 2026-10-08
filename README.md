# Prospekto
CRM interne de prospection B2B, en français, sans inscription ni envoi automatique.

## État — socle fonctionnel, production bloquée
Le dépôt couvre une authentification administrateur, sessions protégées par CSRF, campagnes, prospects, opposition globale et export CSV. Les profils SMTP peuvent être enregistrés, mais aucun message n'est envoyé : l'envoi réel, les connecteurs, la collecte et l'IA restent désactivés.

Les mots de passe SMTP sont chiffrés avec **Fernet** (cryptographie authentifiée) avant stockage. `SMTP_ENCRYPTION_KEY` est obligatoire pour enregistrer un profil et ne doit jamais être committée. Aucun secret n'est affiché ni écrit dans les logs. La clé doit être générée hors dépôt.

## Base de données
Le runtime testé et supporté par ce commit est **SQLite uniquement**. La compatibilité PostgreSQL n'est pas implémentée et aucune validation PostgreSQL n'a été exécutée. Le `docker-compose.yml` PostgreSQL est explicitement marqué et profilé `blocked-postgresql` : ne pas le déployer. Une future version devra fournir un véritable adaptateur (SQLAlchemy ou psycopg), des migrations compatibles et des tests contre PostgreSQL réel avant d'activer Compose.

## Développement et tests
```bash
python -m app.password_hash
python -m unittest discover -s tests -v
```

Copier `.env.example` vers `.env`, définir `ADMIN_PASSWORD_HASH`, `SESSION_SECRET` et une clé Fernet `SMTP_ENCRYPTION_KEY`. Ne jamais committer `.env`.

## Limitations explicites
Pas de SMTP, pas d'envoi réel, pas de retry, pas de connecteurs entreprise, pas de collecte automatique, pas d'IA Mammouth. La conformité, les sauvegardes, la supervision, la rotation des secrets et la revue d'infrastructure restent à valider. Le placeholder historique est conservé et cette documentation fait foi sur les blocages.
