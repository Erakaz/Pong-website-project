#!/bin/sh

set -eu

CERT_DIR=/etc/nginx/certs
CERT="$CERT_DIR/server.crt"
KEY="$CERT_DIR/server.key"

if [ -s "$CERT" ] && [ -s "$KEY" ]; then
    echo "[nginx] certificat TLS deja present, generation ignoree"
    exit 0
fi

mkdir -p "$CERT_DIR"

echo "[nginx] generation du certificat TLS auto-signe..."
openssl req -x509 -nodes -newkey rsa:2048 -sha256 -days 365 \
    -keyout "$KEY" -out "$CERT" \
    -subj "/C=LU/ST=Luxembourg/L=Luxembourg/O=42/OU=ft_transcendence/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:nginx,IP:127.0.0.1" \
    2>/dev/null

chmod 600 "$KEY"
chmod 644 "$CERT"
echo "[nginx] certificat TLS pret"
