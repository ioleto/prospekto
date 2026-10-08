# Envoi individuel revu

`POST /send/reviewed` exige une session, un jeton CSRF, un contact, un profil SMTP et une clé d'idempotence. Les mots de passe SMTP sont chiffrés avec `PROSPEKTO_MASTER_KEY` et ne sont jamais renvoyés par l'API. Une suppression globale bloque le destinataire.

Chaque tentative est durable. Si la connexion échoue après une ambiguïté réseau, l'état devient `uncertain` et `retry_allowed=false`; aucun retry automatique n'est exécuté. La reprise éventuelle doit être une décision opérateur explicite, après revue.
