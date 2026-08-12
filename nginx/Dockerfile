# Contexte de build = racine du projet (voir docker-compose.yml), car cette
# image embarque a la fois la configuration nginx et le frontend statique.
FROM nginx:1.27-alpine

# openssl sert uniquement a generer le certificat auto-signe au demarrage.
RUN apk add --no-cache openssl

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/entrypoint.sh /docker-entrypoint.d/10-selfsigned-cert.sh
COPY frontend /srv/frontend

RUN chmod +x /docker-entrypoint.d/10-selfsigned-cert.sh \
    && mkdir -p /etc/nginx/certs /srv/media

EXPOSE 8080 8443
