# syntax=docker/dockerfile:1.6

FROM node:20-alpine AS build
WORKDIR /app

# IMPORTANT: do NOT set NODE_ENV=production here, otherwise npm install
# skips devDependencies (typescript, vite, plugin-react) and the build
# step fails with `tsc: not found` (exit 127).
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
