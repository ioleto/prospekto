# Déploiement PostgreSQL

Le réseau Docker n'est pas présumé : Compose crée son réseau projet. En Portainer, déployer la stack depuis ce fichier et fournir `POSTGRES_PASSWORD` et une clé Fernet `PROSPEKTO_MASTER_KEY` via des secrets/environnement chiffrés, jamais dans Git. Pour prospekto.ioleto.fr, placer un reverse proxy TLS devant le port publié localement, définir `COOKIE_SECURE=true`, et configurer DNS/TLS hors de cette application. Aucune configuration réseau, SMTP ou fournisseur payant n'est incluse.

`docker compose up -d --build` applique les migrations versionnées au démarrage. Vérifier `GET /healthz`. Les tests SMTP réels et l'envoi réel sont volontairement non effectués.
