# Multi-stage: build Angular (node:22) -> servir con nginx.
# Contexto de build esperado: raiz del monorepo (compose.yml -> context: ., dockerfile: apps/web/Dockerfile)

FROM node:22-alpine AS build
WORKDIR /repo

# 1) Workspace manifests: keep dependency installation cacheable.
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/client/package.json ./packages/client/package.json
RUN npm ci --no-audit --no-fund

# Angular and client project metadata (sources are copied below).
COPY apps/web/angular.json apps/web/tsconfig*.json ./apps/web/
COPY packages/client/tsconfig*.json ./packages/client/

# 2) Fuente de la app y build de produccion.
# Se copian solo src/ y public/ (los manifiestos ya vienen de la etapa 1):
# node_modules y .angular del host quedan excluidos por el .dockerignore de la raiz,
# asi este COPY no pisa los node_modules recien instalados.
COPY apps/web/src ./apps/web/src
COPY apps/web/public ./apps/web/public
COPY packages/client ./packages/client
RUN npm run build -w apps/web -- --configuration production

FROM nginx:1.27-alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
# @angular/build application builder: salida en dist/<proyecto>/browser.
COPY --from=build /repo/apps/web/dist/DeepBDE-web/browser /usr/share/nginx/html
EXPOSE 80
