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
```bash
git clone https://github.com/chem-gl/deepBDE.git && cd deepBDE
cp .env.example .env  # ajusta SECRET_KEY y variables de producción
docker compose -f compose.yml -f compose.prod.yml up -d --build
```
Nginx del host debe proxear el dominio a `127.0.0.1:8082`.
Configura el certificado TLS con Certbot en el host.

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
