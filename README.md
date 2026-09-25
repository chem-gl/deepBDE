# deepBDE

Monorepo de la app DeepBDE (prediccion de Bond Dissociation Energy).

## Layout

```
apps/api/          Django + drf-spectacular (submodulo ML en apps/api/deepbde)
apps/web/          Angular 20 (nginx + proxy /api en produccion)
packages/client/   Cliente TS generado (openapi-generator); fuera de los scans de Sonar
contracts/         openapi.yaml (espejo; source of truth: apps/api)
scripts/           sonar_scan.sh (api|web|all)
compose.yml        Unico compose del repo: backend :8000, redis, web :8080
```

## Docker

```bash
cp .env.example .env          # ajusta SECRET_KEY etc.
docker compose up --build     # web en http://localhost:8080, api en :8000
```

`apps/api/compose.yml` esta deprecated; usa el compose raiz.

## Despliegue (plata)
Primer setup manual en el servidor:

1. Clona el repositorio en `/root/deepBDE` y prepara `.env` (el script también
   puede crear una configuración inicial segura si falta; si ya existe, no la toca).
2. Instala el vhost `deploy/nginx/deepbde.ginodilabio.com.conf`, comprueba Nginx
   y ejecuta Certbot (`certbot --nginx`) para rellenar el certificado TLS.
3. El backend queda en `127.0.0.1:8002` y la web en `127.0.0.1:8082`.

Después del setup, cada push a `main` ejecuta GitHub Actions, que conecta por
SSH a `plata` y ejecuta `scripts/deploy_plata.sh`. El script sincroniza el
checkout, reutiliza los contenedores con Compose (recrea solo lo cambiado),
ejecuta los healthchecks y hace rollback automático a la versión previa si
fallan. Cada despliegue también limpia imágenes y limita el cache de build.
Los smoke tests externos deben pasar. Configura los secretos `DEPLOY_HOST`,
`DEPLOY_USER`, `DEPLOY_PORT` y `DEPLOY_SSH_KEY` en GitHub.

El contexto de build usa `.dockerignore` raiz (excluye `.env`, `.git`, `node_modules`,
`dist`, `.venv`, `apps/api/deepbde`, `.scannerwork`, etc.).

## Dev web

```bash
cd apps/web && npm install
npx ng serve                  # usa environment.ts -> apiBasePath http://localhost:8000
```

El basePath de la API viene de `src/environments/*` (prod: same-origin via nginx).

## Sonar

```bash
scripts/sonar_scan.sh api|web|all   # SONAR_TOKEN del entorno o ~/.config/opencode/.env
```

Keys: `deepbde-api`, `deepbde-web` (localhost:9000). packages/client no se escanea.

## Editor

Abrir `deepBDE.code-workspace` (root + api + web, tsdk y interprete ya apuntados).
Proyectos Serena: raiz (`deepbde`), `apps/api` y `apps/web`.

## Pendientes conocidos

- `apps/web` no versiona `package-lock.json` (gitignored): CI y Docker usan `npm install`,
  no `npm ci`. Pendiente decidir si se versiona el lockfile.
- `SECRET_KEY`: la del `.env`/`.env.example` es preexistente; pendiente rotarla (TODO).
- Mypy del CI es no bloqueante (`continue-on-error`) por deuda de anotaciones con `strict=True`.
- Imports sin usar en `apps/api/api/controllers/` (deuda mayor, fuera del fix actual).
