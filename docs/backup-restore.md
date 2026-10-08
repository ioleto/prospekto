# Sauvegarde/restauration
`docker compose exec -T db pg_dump -U prospekto -d prospekto | age -r AGE_PUBLIC_KEY > prospekto-$(date +%F).sql.age` (clé hors dépôt). Restaurer par `age -d -i AGE_PRIVATE_KEY backup.sql.age | docker compose exec -T db psql -U prospekto -d prospekto`; tester sur une base séparée. Ne jamais sauvegarder `.env`.
