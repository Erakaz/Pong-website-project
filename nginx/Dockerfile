FROM nginx:1.27-alpine

RUN apk add --no-cache openssl

COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/entrypoint.sh /docker-entrypoint.d/10-selfsigned-cert.sh
COPY frontend /srv/frontend

RUN chmod +x /docker-entrypoint.d/10-selfsigned-cert.sh \
    && mkdir -p /etc/nginx/certs /srv/media

EXPOSE 8080 8443
