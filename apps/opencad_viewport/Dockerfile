# syntax=docker/dockerfile:1

FROM node:20-alpine AS build

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

ARG VITE_BASE_URL=http://localhost:8000
ARG VITE_USE_MOCK=false
ARG VITE_USE_CHAT_MOCK=false

ENV VITE_BASE_URL=${VITE_BASE_URL} \
    VITE_USE_MOCK=${VITE_USE_MOCK} \
    VITE_USE_CHAT_MOCK=${VITE_USE_CHAT_MOCK}

RUN pnpm build

FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
