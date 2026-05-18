# syntax=docker/dockerfile:1.6

FROM node:20-alpine AS build
WORKDIR /app

# Vite vshivает VITE_* переменные в build-time. Прокидываем через ARG.
ARG VITE_API_URL=http://localhost:8000
ARG VITE_WS_URL=ws://localhost:8000/ws
ARG VITE_MQTT_WS_URL=ws://localhost:9001
ENV VITE_API_URL=$VITE_API_URL \
    VITE_WS_URL=$VITE_WS_URL \
    VITE_MQTT_WS_URL=$VITE_MQTT_WS_URL

# IMPORTANT: do NOT set NODE_ENV=production before npm install — otherwise
# devDependencies (typescript, vite, plugin-react) get skipped and tsc fails.
COPY package.json ./
RUN --mount=type=cache,target=/root/.npm npm install --no-audit --no-fund --include=dev

COPY tsconfig.json vite.config.ts tailwind.config.js postcss.config.js index.html ./
COPY src ./src
ENV NODE_ENV=production
RUN npm run build

# ---- runtime ----
FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
