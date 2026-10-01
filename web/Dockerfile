# Build: Node compiles the Angular app into static files.
FROM node:20-alpine AS build
WORKDIR /app

# Dependencies first, in their own layer: it is rebuilt only when the two files change.
# npm ci installs exactly what package-lock.json says.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Run: nginx serves the files. Node is not in the final image.
FROM nginx:alpine
COPY --from=build /app/dist/web/browser/ /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
