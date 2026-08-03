#!/usr/bin/env bash
# Build + push all 3 service images to GCR/Artifact Registry, then deploy to GKE.
# Usage: PROJECT_ID=my-gcp-project ./build-and-push.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID env var, e.g. PROJECT_ID=my-gcp-project ./build-and-push.sh}"
TAG="${TAG:-latest}"

for svc in frontend orders inventory; do
  echo "Building $svc..."
  docker build -t "gcr.io/${PROJECT_ID}/otel-demo-${svc}:${TAG}" "./${svc}"
  docker push "gcr.io/${PROJECT_ID}/otel-demo-${svc}:${TAG}"
done

echo "Done. Update image refs in k8s/*.yaml (replace YOUR_PROJECT_ID) then:"
echo "  kubectl apply -f k8s/inventory.yaml"
echo "  kubectl apply -f k8s/orders.yaml"
echo "  kubectl apply -f k8s/frontend.yaml"
