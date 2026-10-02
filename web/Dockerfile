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
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/private/ /etc/nginx/private/

# Open by default, so that a local run does not ask for a login. The deployed
# container sets SITE_PRIVATE=on (config/deploy.web.yml), and nginx then asks the
# ticket API whether the login in a request is valid.
ENV SITE_PRIVATE=off

# Where the ticket API and the agent server are. The defaults are the service names in
# compose.yaml; the deployed container gets the names the other containers have there.
ENV API_HOST=api
ENV AGENT_HOST=agent

# Only these variables are replaced in the template. Without the filter, nginx's own
# $variables would be replaced too, with nothing.
ENV NGINX_ENVSUBST_FILTER=^(SITE_PRIVATE|API_HOST|AGENT_HOST)$

EXPOSE 80
