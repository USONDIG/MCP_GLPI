# Déploiement Render gratuit

Le point d'entrée `http_server.py` expose MCP Streamable HTTP sur `/mcp`,
sans sessions HTTP persistantes. `server.py` conserve le transport stdio.

## Paramètres du Web Service

- Runtime : Python ; version `3.12.14` (`PYTHON_VERSION`).
- Plan : **Free** ; région : Frankfurt.
- Build : `pip install uv==0.12.19 && uv sync --frozen --no-dev`
- Start : `.venv/bin/python http_server.py`
- Health check : `/healthz`
- Port : fourni automatiquement par Render, écoute sur `0.0.0.0`.

## Variables d'environnement

À saisir dans Render → Environment, en texte brut (pas en base64) :

| Variable | Valeur |
| --- | --- |
| `GLPI_URL` | URL HTTPS de base de GLPI, sans suffixe API |
| `GLPI_APP_TOKEN` | App-Token existant du client API GLPI |
| `GLPI_USER_TOKEN` | User-Token existant du compte GLPI |
| `GLPI_VERSION` | `10` ou `11`, selon l'instance |
| `GLPI_LANG` | `fr` |
| `GLPI_VERIFY_TLS` | `true` |
| `MCP_AUTH_TOKEN` | Jeton aléatoire distinct, au moins 32 caractères |

Ne jamais déposer les secrets dans Git ni créer de `config.json` sur Render.
Le jeton MCP peut être généré localement avec
`python -c 'import secrets; print(secrets.token_urlsafe(48))'` puis conservé
dans un gestionnaire de mots de passe. Il ne remplace aucun jeton GLPI.
Tous les clients autorisés utilisent le même compte GLPI et ses permissions.

## Connexion du client

URL : `https://<nom-du-service>.onrender.com/mcp`.
Configurer l'en-tête `Authorization: Bearer <MCP_AUTH_TOKEN>` dans le client.
Le client doit accepter un jeton Bearer personnalisé ; ce serveur ne fournit
pas de parcours OAuth. Ne jamais placer de jeton dans l'URL.

## Vérification

`/healthz` répond 200 dès que le processus est actif. Ce contrôle ne garantit
pas l'accès à GLPI. Tant que la configuration manque, `/mcp` reste fermé :
503 si aucun jeton MCP valide n'est configuré, sinon 401 sans authentification,
ou 503 pour un client authentifié si les variables GLPI manquent.
Après saisie des variables, redéployer, vérifier l'initialisation MCP,
`tools/list`, puis une lecture GLPI autorisée.

GLPI doit être joignable depuis Render avec un certificat HTTPS valide.
Une instance accessible uniquement sur l'intranet nécessite une solution réseau.
Le routage API GLPI 10/11 est celui du dépôt amont et doit être vérifié
sur l'instance réelle.

Render Free se met en veille après 15 minutes sans trafic et peut prendre
environ une minute à redémarrer. Les 750 heures mensuelles gratuites sont
partagées entre les services gratuits de l'espace de travail.
Voir https://render.com/docs/free.
