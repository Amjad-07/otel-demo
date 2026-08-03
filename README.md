# OTel Demo: frontend (HTTP) → orders (gRPC) → inventory (HTTP)

Three Python services, each independently instrumented with the OpenTelemetry
SDK (traces, metrics, logs — all via OTLP/gRPC), simulating a realistic
polyglot-protocol microservice chain:

```
client --HTTP POST /purchase--> frontend --gRPC CreateOrder--> orders --HTTP POST /check-stock--> inventory
```

This gives you one HTTP hop, one gRPC hop, and one more HTTP hop, so you get
both protocol types instrumented and propagated end-to-end (W3C tracecontext
propagates automatically across all three).

## What's instrumented

- **Traces**: auto-instrumented FastAPI/gRPC/requests spans + manual child spans
  with custom attributes (`item.id`, `order.status`, etc).
- **Metrics**: custom counters/histograms per service (`orders.created`,
  `inventory.stock_checks`, `frontend.request_latency_ms`, ...).
- **Logs**: stdlib `logging` bridged into OTel via `LoggingHandler`, correlated
  with trace/span IDs automatically.

All three signals export via OTLP/gRPC to whatever endpoint you set in
`OTEL_EXPORTER_OTLP_ENDPOINT` — point that at your own Collector, and fan out
to Prometheus/Datadog/etc from there. No app code changes needed to swap
backends.

## Repo layout

```
frontend/     FastAPI HTTP service, gRPC client to orders
orders/       gRPC server, HTTP client to inventory
inventory/    FastAPI HTTP service (leaf node, fake stock data)
proto/        orders.proto (shared gRPC contract)
k8s/          Deployment+Service manifests for GKE
build-and-push.sh
```

## Run locally with Docker Compose (fastest way to sanity-check before GKE)

You'll need a collector running locally too (or just point at a debug OTLP
receiver). Minimal compose to test end-to-end:

```yaml
version: "3.8"
services:
  inventory:
    build: ./inventory
    ports: ["8081:8081"]
    environment:
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
  orders:
    build: ./orders
    ports: ["50051:50051"]
    environment:
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
      INVENTORY_URL: "http://inventory:8081"
    depends_on: [inventory]
  frontend:
    build: ./frontend
    ports: ["8080:8080"]
    environment:
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
      ORDERS_ADDR: "orders:50051"
    depends_on: [orders]
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml
    ports: ["4317:4317"]
```

Test it:

```bash
curl -X POST localhost:8080/purchase -H 'content-type: application/json' \
  -d '{"item_id": "item-1", "quantity": 2}'

# item-2 has 0 stock — try it to see the REJECTED path and error-ish spans:
curl -X POST localhost:8080/purchase -H 'content-type: application/json' \
  -d '{"item_id": "item-2", "quantity": 1}'
```

## Deploy to GKE

1. Build & push images:
   ```bash
   PROJECT_ID=your-gcp-project ./build-and-push.sh
   ```
2. Replace `YOUR_PROJECT_ID` in `k8s/*.yaml` with your actual project id
   (or `sed -i "s/YOUR_PROJECT_ID/your-gcp-project/g" k8s/*.yaml`).
3. Point `OTEL_EXPORTER_OTLP_ENDPOINT` in each manifest at wherever you're
   running your Collector (e.g. a `otel-collector` Service in an
   `observability` namespace, or a DaemonSet endpoint per node).
4. Apply:
   ```bash
   kubectl apply -f k8s/inventory.yaml
   kubectl apply -f k8s/orders.yaml
   kubectl apply -f k8s/frontend.yaml
   ```
5. Get the frontend's external IP and hit `/purchase` as above:
   ```bash
   kubectl get svc frontend
   ```

## Notes for your Collector setup

- All three services default to `insecure=True` OTLP/gRPC (no TLS) — fine
  in-cluster, but flip `insecure=False` + configure certs if you're exporting
  outside the cluster.
- `service.name` is set per-service (`frontend`/`orders`/`inventory`) plus
  `service.namespace=otel-demo` and `deployment.environment` — good grouping
  dimensions for whatever backend you wire up downstream.
- Since only `OTEL_EXPORTER_OTLP_ENDPOINT` is hardwired to a Collector (not
  Datadog/Prometheus directly), you can freely add/change exporters in the
  Collector config (`otlp` → `prometheusremotewrite`, `datadog`, etc.) without
  touching any of this app code.
