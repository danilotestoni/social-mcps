#!/usr/bin/env bash
# Rota un campo de credencial (LinkedIn, Facebook, Instagram, Threads,
# WordPress, X, MCP_AUTH_TOKEN...) dentro del secreto único de Secret
# Manager `social-mcps-credentials` (JSON con todas las credenciales de
# unified-mcp). Cloud Run recoge la nueva versión ("latest") en el próximo
# arranque de instancia; usa --restart para forzarlo ahora mismo.
#
# Uso:
#   ./rotate-secret.sh <CLAVE_JSON> <valor|-> [--restart]
#
# Ejemplos:
#   ./rotate-secret.sh LINKEDIN_ACCESS_TOKEN "nuevo-token-aqui"
#   echo -n "nuevo-token" | ./rotate-secret.sh FACEBOOK_ACCESS_TOKEN - --restart
#
# Claves JSON válidas (deben existir ya dentro del secreto):
#   MCP_AUTH_TOKEN
#   LINKEDIN_CLIENT_ID LINKEDIN_CLIENT_SECRET LINKEDIN_ACCESS_TOKEN
#   LINKEDIN_REFRESH_TOKEN LINKEDIN_TOKEN_EXPIRY LINKEDIN_PERSON_URN
#   FACEBOOK_APP_ID FACEBOOK_APP_SECRET FACEBOOK_ACCESS_TOKEN
#   FACEBOOK_TOKEN_EXPIRY FACEBOOK_PAGE_ID
#   INSTAGRAM_APP_ID INSTAGRAM_APP_SECRET INSTAGRAM_ACCESS_TOKEN
#   INSTAGRAM_ACCOUNT_ID INSTAGRAM_TOKEN_EXPIRY
#   THREADS_APP_ID THREADS_APP_SECRET THREADS_ACCESS_TOKEN THREADS_USER_ID
#   THREADS_TOKEN_EXPIRY
#   WP_CLIENT_ID WP_CLIENT_SECRET WP_ACCESS_TOKEN WP_SITE_ID
#   X_USERNAME X_PASSWORD X_EMAIL
#
# `gateway-client-token` NO vive aquí — es un secreto aparte de Cloudflare
# Workers (Wrangler), no de este proyecto GCP. Este script no lo toca.
#
# Este script lee el JSON completo del secreto para modificar un solo campo
# y volver a subirlo. Evita imprimir el JSON completo (contiene todas las
# credenciales) en la terminal o en logs.

set -euo pipefail

PROJECT="${SOCIALMCPS_GCP_PROJECT:-socialmcps}"
SERVICE="${SOCIALMCPS_CLOUD_RUN_SERVICE:-unified-mcp}"
REGION="${SOCIALMCPS_CLOUD_RUN_REGION:-europe-west1}"
SECRET_NAME="social-mcps-credentials"

usage() {
  echo "Uso: $0 <CLAVE_JSON> <valor|-> [--restart]" >&2
  echo "  <valor|-> : valor nuevo del campo, o '-' para leerlo de stdin" >&2
  echo "  --restart : fuerza un redeploy de Cloud Run para recoger el valor ya" >&2
  exit 1
}

[ $# -lt 2 ] && usage

FIELD="$1"
VALUE_ARG="$2"
RESTART=false
[ "${3:-}" = "--restart" ] && RESTART=true

if ! gcloud secrets describe "$SECRET_NAME" --project="$PROJECT" >/dev/null 2>&1; then
  echo "ERROR: el secreto '$SECRET_NAME' no existe en el proyecto '$PROJECT'." >&2
  exit 1
fi

if [ "$VALUE_ARG" = "-" ]; then
  NEW_VALUE="$(cat)"
else
  NEW_VALUE="$VALUE_ARG"
fi

if [ -z "$NEW_VALUE" ]; then
  echo "ERROR: el valor proporcionado está vacío." >&2
  exit 1
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

# Descarga el JSON actual, sustituye un solo campo con jq y vuelve a subirlo
# como nueva versión — sin volcar el contenido completo a stdout/logs.
gcloud secrets versions access latest --secret="$SECRET_NAME" --project="$PROJECT" \
  | jq --arg k "$FIELD" --arg v "$NEW_VALUE" '.[$k] = $v' > "$TMP_FILE"

if [ ! -s "$TMP_FILE" ]; then
  echo "ERROR: no se pudo construir el JSON actualizado." >&2
  exit 1
fi

PREVIOUS_VERSION="$(gcloud secrets versions list "$SECRET_NAME" --project="$PROJECT" \
  --filter="state=enabled" --sort-by="~name" --format="value(name)" | head -n1)"

gcloud secrets versions add "$SECRET_NAME" --project="$PROJECT" --data-file="$TMP_FILE" >/dev/null
echo "OK: nueva versión creada para '$FIELD' en el secreto '$SECRET_NAME'."

# Destruye la versión anterior para no acumular versiones activas — es lo
# que causaba el sobrecoste antes de consolidar los 29 secretos en uno.
if [ -n "$PREVIOUS_VERSION" ]; then
  gcloud secrets versions destroy "$PREVIOUS_VERSION" --secret="$SECRET_NAME" \
    --project="$PROJECT" --quiet
  echo "OK: versión anterior ($PREVIOUS_VERSION) destruida."
fi

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
