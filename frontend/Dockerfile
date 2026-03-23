# ============================================================
# Stage 1: Builder — compile React + TypeScript
# ============================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (layer caching)
COPY package.json package-lock.json* ./
RUN npm ci --silent

# Build-time API URL (overridable via --build-arg)
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL

COPY . .
RUN npm run build

# ============================================================
# Stage 2: Nginx — serve static files
# ============================================================
FROM nginx:1.27-alpine AS runtime

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/health 2>/dev/null | grep -q ok || wget -qO- http://localhost/ > /dev/null

CMD ["nginx", "-g", "daemon off;"]
