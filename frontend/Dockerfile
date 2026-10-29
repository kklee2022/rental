FROM node:24-alpine AS deps

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM deps AS builder

WORKDIR /app/frontend
COPY docs /app/docs
COPY frontend .
RUN npm run build

FROM node:24-alpine AS runner

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=builder --chown=app:app /app/frontend/.next/standalone ./
COPY --from=builder --chown=app:app /app/frontend/.next/static ./.next/static
COPY --from=builder --chown=app:app /app/frontend/public ./public

USER app
EXPOSE 3000

CMD ["node", "server.js"]
