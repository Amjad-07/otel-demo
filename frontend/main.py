import logging
import os
import time

import grpc
from fastapi import FastAPI
from pydantic import BaseModel
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient

from otel_setup import init_otel
import orders_pb2
import orders_pb2_grpc

SERVICE_NAME = "frontend"
tracer, meter = init_otel(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(title="frontend")
FastAPIInstrumentor.instrument_app(app)
GrpcInstrumentorClient().instrument()

ORDERS_ADDR = os.getenv("ORDERS_ADDR", "orders:50051")

request_counter = meter.create_counter(
    "frontend.requests", description="Number of purchase requests received"
)
request_latency_hist = meter.create_histogram(
    "frontend.request_latency_ms", description="End-to-end request latency", unit="ms"
)

_channel = grpc.insecure_channel(ORDERS_ADDR)
_orders_stub = orders_pb2_grpc.OrderServiceStub(_channel)


class PurchaseRequest(BaseModel):
    item_id: str
    quantity: int = 1


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/purchase")
def purchase(req: PurchaseRequest):
    start = time.time()
    with tracer.start_as_current_span("handle-purchase") as span:
        span.set_attribute("item.id", req.item_id)
        span.set_attribute("item.quantity", req.quantity)

        try:
            grpc_req = orders_pb2.CreateOrderRequest(
                item_id=req.item_id, quantity=req.quantity
            )
            grpc_resp = _orders_stub.CreateOrder(grpc_req, timeout=10)
        except grpc.RpcError as e:
            logger.error("orders gRPC call failed: %s", e)
            span.record_exception(e)
            request_counter.add(1, {"status": "error"})
            return {"status": "ERROR", "detail": "orders service unavailable"}

        result = {
            "order_id": grpc_resp.order_id,
            "status": grpc_resp.status,
            "in_stock": grpc_resp.in_stock,
        }
        logger.info("purchase result=%s", result)

    request_counter.add(1, {"status": result["status"]})
    request_latency_hist.record((time.time() - start) * 1000)
    return result
