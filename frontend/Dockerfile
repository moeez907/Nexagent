# Stage 1: Build the React/Vite application
FROM node:20-alpine AS builder

WORKDIR /app

# Prevent Electron from downloading desktop binaries during build
ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1

# Copy package descriptors and install dependencies
COPY package*.json ./
RUN npm ci --ignore-scripts || npm install --ignore-scripts

# Copy frontend source files
COPY . .

# Build the production bundle
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy built production assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
