# Frontend image: build the Vite SPA, then serve the static dist on port 5173.
# Multi-stage so the runtime image doesn't carry the full dev toolchain's node_modules.

# ---- build stage ----
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# VITE_* values are inlined at build time. Override with --build-arg if needed.
ARG VITE_API_BASE=http://localhost:8000
ARG VITE_API_TOKEN=dev-secret-change-me
ENV VITE_API_BASE=$VITE_API_BASE
ENV VITE_API_TOKEN=$VITE_API_TOKEN

RUN npm run build

# ---- runtime stage ----
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

# `serve` is a tiny static file server. We copy only the built assets.
RUN npm install -g serve@14
COPY --from=build /app/dist ./dist

EXPOSE 5173
# -s = single-page-app fallback (serve index.html for unknown routes).
CMD ["serve", "-s", "dist", "-l", "5173"]
