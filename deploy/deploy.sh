#!/usr/bin/env bash
# First Cloud Run deploy — API only (docs/ENDGAME.md, Aug 30 → pulled to Aug 29).
#
# The two things that differ from local, and why each step below exists:
#
#   1. ADC does not exist on Cloud Run. The service runs AS its own service
#      account, so that account needs explicit grants: Firestore (the cache),
#      Vertex AI (the reader), and read access to the Parallel key secret.
#   2. PARALLEL_API_KEY comes from Secret Manager (--set-secrets), never from
#      --set-env-vars, so it is not in the service definition or the console.
#
# And the one component never exercised: CACHE_BACKEND=firestore. The smoke
# test at the end proves it with /api/health (a real write/read probe and a
# document count) before and after a query. (/healthz is reserved by the
# Cloud Run edge, which answers it with a 404 before the container sees it.)
#
# Usage:
#   export PARALLEL_API_KEY=...          # only needed the first time (creates the secret version)
#   deploy/deploy.sh                     # uses the gcloud default project
#   PROJECT=my-proj REGION=us-central1 deploy/deploy.sh
#
# Re-runnable: every step is create-if-missing.

set -euo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-can-i-use-this}"
SA_NAME="${SA_NAME:-ciut-runtime}"
SA_EMAIL="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
SECRET="${SECRET:-parallel-api-key}"

[[ -n "$PROJECT" ]] || { echo "No project: set PROJECT or 'gcloud config set project'"; exit 1; }

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

step "Preflight — $PROJECT / $REGION / $SERVICE"
gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q . || { echo "Not logged in: gcloud auth login"; exit 1; }
gcloud config set project "$PROJECT" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"

step "1/6 APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com

step "2/6 Firestore database (Native mode, $REGION)"
if ! gcloud firestore databases describe --database='(default)' >/dev/null 2>&1; then
  gcloud firestore databases create --database='(default)' --location="$REGION" --type=firestore-native
else
  echo "exists"
fi

step "3/6 Secret Manager — $SECRET"
if ! gcloud secrets describe "$SECRET" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET" --replication-policy=automatic
fi
if [[ -n "${PARALLEL_API_KEY:-}" ]]; then
  printf '%s' "$PARALLEL_API_KEY" | gcloud secrets versions add "$SECRET" --data-file=-
  echo "added a new version from \$PARALLEL_API_KEY"
elif ! gcloud secrets versions list "$SECRET" --format='value(name)' | grep -q .; then
  echo "The secret has no versions and PARALLEL_API_KEY is not set in this shell. Export it and re-run."; exit 1
else
  echo "keeping the existing version (PARALLEL_API_KEY not set in this shell)"
fi

step "4/6 Runtime service account — $SA_EMAIL"
if ! gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SA_NAME" --display-name="Can I Use This — Cloud Run runtime"
fi
# The service authenticates as this account (no ADC on Cloud Run): Firestore for
# the cache, Vertex AI for the reader, and the one secret it needs.
for role in roles/datastore.user roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA_EMAIL" --role="$role" \
    --condition=None --quiet >/dev/null
  echo "granted $role"
done
gcloud secrets add-iam-policy-binding "$SECRET" --member="serviceAccount:$SA_EMAIL" \
  --role=roles/secretmanager.secretAccessor --quiet >/dev/null
echo "granted secretAccessor on $SECRET"

# `gcloud run deploy --source` builds with Cloud Build as the default compute
# service account. On projects created after mid-2024 that account no longer
# has Editor, so it needs the builder role or the build fails with a
# permissions error that looks like a Cloud Run problem.
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for role in roles/cloudbuild.builds.builder roles/artifactregistry.writer roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$COMPUTE_SA" --role="$role" \
    --condition=None --quiet >/dev/null
done
echo "granted build roles to $COMPUTE_SA"

step "5/6 Deploy — gcloud run deploy --source ."
# --min-instances 1: no cold starts during judging (Sep 23 – Oct 7); keep it.
# --timeout 300:     a cold query is under 90 s; SSE streams stay open that long.
# --concurrency 8:   each query holds a thread for up to 90 s; instances scale out beyond that.
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --service-account "$SA_EMAIL" \
  --set-secrets "PARALLEL_API_KEY=${SECRET}:latest" \
  --set-env-vars "CACHE_BACKEND=firestore,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=1" \
  --min-instances 1 --max-instances 3 --concurrency 8 \
  --cpu 1 --memory 1Gi --timeout 300 \
  --allow-unauthenticated \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"

step "6/6 Smoke — $URL"
echo "-- /api/health before a query (cache probe must show roundtrip=true, backend=firestore)"
curl -sS "$URL/api/health" | python -m json.tool
echo
echo "-- streamed query, cold (West End Blues / Louis Armstrong): progress events, then the response"
curl -sS -N --max-time 180 "$URL/api/query/stream?title=West%20End%20Blues&artist=Louis%20Armstrong" \
  | grep -E '^(event|data)' | sed -E 's/^(data: .{0,160}).*/\1 …/'
echo
echo "-- /api/health after: the Firestore document count should have grown"
curl -sS "$URL/api/health" | python -m json.tool
echo
echo "-- same query, warm (should be well under 5 s)"
time curl -sS -o /dev/null -X POST "$URL/api/query" -H 'content-type: application/json' \
  -d '{"title":"West End Blues","artist":"Louis Armstrong"}'
echo
echo "Deployed: $URL"
echo "Next: keep --min-instances 1 through Oct 7; billing alert stays on; redeploy with the UI on Sep 4 by re-running this script."
