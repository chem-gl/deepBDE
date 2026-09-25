# deepBDE

Predicción de Bond Dissociation Energy. Monorepo: Django + Angular 20 + cliente TS generado.

## Producción

| | |
|---|---|
| URL | https://deepbde.ginodilabio.com/ (+ www) |
| Servidor | `plata`, nginx host con TLS Let's Encrypt (expira 2026-12-24, auto-renew) |
| Stack | `deepbde-web` 127.0.0.1:8082 (nginx SPA + proxy `/api/`) · `deepbde-backend` 127.0.0.1:8002 (Django + torch, healthy) · `deepbde-redis` (interno) |
| Legacy | `test1`/`test2`.guzman-lopez.com apuntan al mismo stack. Su DNS externo no resuelve a plata (incidencia en `README-plata.md` del servidor). |

## Arquitectura

```
internet → nginx host (:443 deepbde.ginodilabio.com)
             → deepbde-web :8082 (SPA + /api/ proxy)
             → deepbde-backend :8002 → deepbde-redis
```

| Carpeta | Contenido |
|---|---|
| `apps/api/` | Django DRF + drf-spectacular; ML en submódulo `apps/api/deepbde` |
| `apps/web/` | Angular 20 (prod: same-origin vía nginx) |
| `packages/client/` | Cliente TS generado con OpenAPI (`deepbde-client`); fuera de scans Sonar |
| `contracts/openapi.yaml` | Espejo; source of truth: `apps/api` |
| `scripts/` | `deploy_plata.sh`, `sonar_scan.sh` |
| `deploy/nginx/` | Plantilla vhost |

## Quickstart local

```bash
cp .env.example .env
docker compose up --build   # web :8080, api :8000, redis :6379
```

```bash
cd apps/web && npm install && npx ng serve   # apiBasePath http://localhost:8000 (src/environments/*)
scripts/sonar_scan.sh api|web|all            # SONAR_TOKEN del entorno o ~/.config/opencode/.env
```

Producción usa `compose.prod.yml` (puertos `127.0.0.1:8002/8082`, redis interno).
Build con `.dockerignore` raíz (excluye `.env`, `.git`, `node_modules`, `dist`, `.venv`, `apps/api/deepbde`, `.scannerwork`).

## CI/CD

Push a `main` dispara dos workflows:

| Workflow | Qué hace |
|---|---|
| `CI` | Web typecheck; API `ruff` + `mypy` no-bloqueante |
| `Deploy production` | SSH a plata → `scripts/deploy_plata.sh`: sync git, guard disco <8 GB, `compose build + up -d --remove-orphans` reutilizando contenedores, healthchecks 180 s, rollback automático al SHA previo si fallan, prune imágenes + builder cache ≤5 GB; smokes externos bloqueantes |

Secretos: `DEPLOY_HOST/USER/PORT/SSH_KEY` (llave ed25519 dedicada `~/.ssh/deepbde_deploy_plata`).
Primer run verde: `36124480328` (14 s con cache).

## E2E en prod (2026-09-25): PASS

Playwright contra producción: carga, redirects, SPA `/about` `/citation` wildcard, health 200, 0 requests fallidos, móvil 390x844 OK. Flujo SMILES `CCO` → predict/info → visor SVG → BDEEvaluate → tabla BDE real (O-H 106.01, O-C 95.47, C-C 87.65). Batch con ZIP/CSV y SMILES inválido manejado.

## Quality

SonarQube `localhost:9000`, proyectos `deepbde-api` / `deepbde-web`. Scan solo local (`scripts/sonar_scan.sh`); no corre en GHA por diseño.

## Editor

Abrir `deepBDE.code-workspace` (root + api + web, tsdk e intérprete apuntados). Proyectos Serena: raíz (`deepbde`), `apps/api`, `apps/web`.

## Pendientes conocidos

- Ruff en rojo: F401/E402/F841 en `apps/api/api/controllers` (CI lint bloqueado hasta limpiar). Mypy strict sin anotaciones (no-bloqueante).
- `console.log` de debug en bundle prod web (`[BDE FLOW]`/`[CANON]`/`[DEBUG]`); filtra por environment.
- Eager-load ~15 MB (Ketcher 7.9 MB + RDKit wasm 6.9 MB); candidato a lazy-load.
- `package-lock.json` gitignored: `npm install` no determinista.
- UX silenciosa con `bond_idx` fuera de rango.
- Rotación `SECRET_KEY` histórica pendiente.
