# syntax=docker/dockerfile:1
#
# Build context is the REPOSITORY ROOT, not this directory — the app depends
# on the opencad-viewport workspace library:
#
#   docker build -f apps/opencad_viewport/Dockerfile -t opencad-viewport .

FROM node:20-alpine AS build

WORKDIR /repo

RUN corepack enable

# Manifests first so dependency installation caches independently of sources.
COPY pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/opencad-viewport/package.json ./packages/opencad-viewport/
COPY apps/opencad_viewport/package.json ./apps/opencad_viewport/
RUN pnpm install --frozen-lockfile

COPY packages/opencad-viewport ./packages/opencad-viewport
COPY apps/opencad_viewport ./apps/opencad_viewport

ARG VITE_BASE_URL=http://localhost:8000
ARG VITE_USE_MOCK=false
ARG VITE_USE_CHAT_MOCK=false

ENV VITE_BASE_URL=${VITE_BASE_URL} \
    VITE_USE_MOCK=${VITE_USE_MOCK} \
    VITE_USE_CHAT_MOCK=${VITE_USE_CHAT_MOCK}

RUN pnpm --filter opencad-viewport build \
    && pnpm --filter opencad-viewport-app build

FROM nginx:1.27-alpine AS runtime

COPY apps/opencad_viewport/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/opencad_viewport/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
