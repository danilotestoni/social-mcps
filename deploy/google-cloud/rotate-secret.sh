#!/usr/bin/env bash
# Rota un secreto de plataforma (LinkedIn, Facebook, Instagram, Threads,
# WordPress, X, Gemini) en Secret Manager cuando un access token caduca o
# se renueva. Cloud Run recoge la nueva versión ("latest") en el próximo
# arranque de instancia; usa --restart para forzarlo ahora mismo.
#
# Uso:
#   ./rotate-secret.sh <nombre-secreto> <valor|-> [--restart]
#
# Ejemplos:
#   ./rotate-secret.sh linkedin-access-token "nuevo-token-aqui"
#   echo -n "nuevo-token" | ./rotate-secret.sh facebook-access-token - --restart
#
# Nombres de secreto válidos (deben existir ya en Secret Manager):
#   linkedin-client-id linkedin-client-secret linkedin-access-token
#   linkedin-refresh-token linkedin-token-expiry linkedin-person-urn
#   facebook-app-id facebook-app-secret facebook-access-token
#   facebook-token-expiry facebook-page-id
#   instagram-app-id instagram-app-secret instagram-access-token instagram-account-id
#   threads-app-id threads-app-secret threads-access-token threads-user-id
#   wp-client-id wp-client-secret wp-access-token wp-site-id
#   x-username x-password x-email
#   gemini-api-key mcp-auth-token gateway-client-token

set -euo pipefail

PROJECT="${SOCIALMCPS_GCP_PROJECT:-socialmcps}"
SERVICE="${SOCIALMCPS_CLOUD_RUN_SERVICE:-unified-mcp}"
REGION="${SOCIALMCPS_CLOUD_RUN_REGION:-europe-west1}"

usage() {
  echo "Uso: $0 <nombre-secreto> <valor|-> [--restart]" >&2
  echo "  <valor|-> : valor nuevo del secreto, o '-' para leerlo de stdin" >&2
  echo "  --restart : fuerza un redeploy de Cloud Run para recoger el valor ya" >&2
  exit 1
}

[ $# -lt 2 ] && usage

SECRET_NAME="$1"
VALUE_ARG="$2"
RESTART=false
[ "${3:-}" = "--restart" ] && RESTART=true

if ! gcloud secrets describe "$SECRET_NAME" --project="$PROJECT" >/dev/null 2>&1; then
  echo "ERROR: el secreto '$SECRET_NAME' no existe en el proyecto '$PROJECT'." >&2
  echo "Este script solo rota secretos ya creados; para crear uno nuevo usa gcloud secrets create." >&2
  exit 1
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

if [ "$VALUE_ARG" = "-" ]; then
  cat > "$TMP_FILE"
else
  printf '%s' "$VALUE_ARG" > "$TMP_FILE"
fi

if [ ! -s "$TMP_FILE" ]; then
  echo "ERROR: el valor proporcionado está vacío." >&2
  exit 1
fi

gcloud secrets versions add "$SECRET_NAME" --project="$PROJECT" --data-file="$TMP_FILE" >/dev/null
echo "OK: nueva versión creada para el secreto '$SECRET_NAME'."

if [ "$RESTART" = true ]; then
  echo "Forzando redeploy de Cloud Run ('$SERVICE') para recoger el nuevo valor..."
  gcloud run services update "$SERVICE" \
    --project="$PROJECT" --region="$REGION" \
    --update-labels="rotated-at=$(date -u +%Y%m%dt%H%M%S)" \
    --quiet
  echo "OK: nueva revisión desplegada."
else
  echo "Nota: Cloud Run seguirá usando el valor anterior hasta que se cree una nueva instancia/revisión."
  echo "Vuelve a ejecutar con --restart si quieres aplicarlo de inmediato."
fi
