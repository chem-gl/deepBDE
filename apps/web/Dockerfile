# Multi-stage: build Angular (node:22) -> servir con nginx.
# Contexto de build esperado: raiz del monorepo (compose.yml -> context: ., dockerfile: apps/web/Dockerfile)

FROM node:22-alpine AS build
WORKDIR /repo

# 1) Cliente compartido + manifiestos: capa de cache de dependencias.
# El cliente vive dentro de apps/web en la imagen para que sus peer dependencies
# resuelvan los paquetes Angular instalados en apps/web/node_modules.
COPY packages/client ./apps/web/vendor/client
COPY apps/web/package.json apps/web/angular.json apps/web/tsconfig*.json ./apps/web/
# Nota: apps/web no versiona package-lock.json (gitignored) -> npm install en vez de npm ci.
RUN sed -i 's#file:../../packages/client#file:./vendor/client#' apps/web/package.json \
    && sed -i 's#../../packages/client#./vendor/client#g' apps/web/tsconfig.json \
    && cd apps/web && npm install --no-audit --no-fund

# 2) Fuente de la app y build de produccion.
# Se copian solo src/ y public/ (los manifiestos ya vienen de la etapa 1):
# node_modules y .angular del host quedan excluidos por el .dockerignore de la raiz,
# asi este COPY no pisa los node_modules recien instalados.
COPY apps/web/src ./apps/web/src
COPY apps/web/public ./apps/web/public
RUN cd apps/web && npx ng build --configuration production

FROM nginx:1.27-alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
# @angular/build application builder: salida en dist/<proyecto>/browser.
COPY --from=build /repo/apps/web/dist/DeepBDE-web/browser /usr/share/nginx/html
EXPOSE 80
