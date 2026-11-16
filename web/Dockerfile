# Next.js UI. NDA_API_URL is read by next.config.ts for the /api/* proxy; it is baked in at build time,
# so it is passed as a build arg and set again at runtime.
FROM node:22-slim

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /web

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG NDA_API_URL=http://api:8000
ENV NDA_API_URL=${NDA_API_URL}
RUN npm run build

ENV NODE_ENV=production
EXPOSE 3000
CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
