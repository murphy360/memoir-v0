# deps: every dependency, at / so a checkout mounted anywhere below resolves /node_modules.
FROM node:26-alpine AS deps
WORKDIR /
COPY package.json package-lock.json ./
RUN npm ci

# test: what CI runs the typecheck and tests in (test-docker mounts the checkout at /src).
FROM deps AS test
ENV PATH=/node_modules/.bin:$PATH NEXT_TELEMETRY_DISABLED=1
WORKDIR /src
COPY . .

# build: the production bundle. NEXT_PUBLIC_* values are inlined here, so they are build arguments.
# The defaults are the hosted deployment (dontpanic.ddns.net/memoir-v0, API on the same origin);
# docker-compose.yml overrides them for local development.
FROM node:26-alpine AS build
ARG NEXT_PUBLIC_BASE_PATH=/memoir-v0
ARG NEXT_PUBLIC_API_BASE_URL=
ENV NEXT_PUBLIC_BASE_PATH=$NEXT_PUBLIC_BASE_PATH \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:26-alpine
ARG NEXT_PUBLIC_BASE_PATH=/memoir-v0
WORKDIR /app
ENV NODE_ENV=production PORT=3000 NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_BASE_PATH=$NEXT_PUBLIC_BASE_PATH
COPY --from=build /app/package.json /app/next.config.mjs ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
USER node
EXPOSE 3000
HEALTHCHECK --interval=60s --timeout=5s CMD wget -qO- "http://127.0.0.1:${PORT}${NEXT_PUBLIC_BASE_PATH}/" >/dev/null || exit 1
CMD ["npm", "run", "start"]
