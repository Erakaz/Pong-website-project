FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Les dependances d'abord : cette couche n'est reconstruite que si
# requirements.txt change, pas a chaque modification du code.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# L'application ne tourne jamais en root dans le conteneur. L'UID fixe 10001
# garde des permissions previsibles sur le volume nomme `media`.
RUN chmod +x /app/entrypoint.sh \
    && adduser --system --group --uid 10001 --no-create-home app \
    && mkdir -p /app/media \
    && chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
