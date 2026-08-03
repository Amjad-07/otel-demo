import logging
import random
import time

from fastapi import FastAPI
from pydantic import BaseModel
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from otel_setup import init_otel

SERVICE_NAME = "inventory"
tracer, meter = init_otel(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(title="inventory")
FastAPIInstrumentor.instrument_app(app)

stock_check_counter = meter.create_counter(
    "inventory.stock_checks", description="Number of stock checks performed"
)
stock_latency_hist = meter.create_histogram(
    "inventory.check_latency_ms", description="Latency of stock check logic", unit="ms"
)

# fake in-memory stock
STOCK = {"item-1": 42, "item-2": 0, "item-3": 7}


class StockCheckRequest(BaseModel):
    item_id: str
    quantity: int


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/check-stock")
def check_stock(req: StockCheckRequest):
    start = time.time()
    with tracer.start_as_current_span("evaluate-stock-rules") as span:
        span.set_attribute("item.id", req.item_id)
        span.set_attribute("item.quantity_requested", req.quantity)

        # simulate variable processing time / occasional slowness
        time.sleep(random.uniform(0.01, 0.08))

        available = STOCK.get(req.item_id, 0)
        in_stock = available >= req.quantity
        span.set_attribute("item.available", available)
        span.set_attribute("item.in_stock", in_stock)

        logger.info(
            "stock check item=%s requested=%s available=%s in_stock=%s",
            req.item_id, req.quantity, available, in_stock,
        )

    stock_check_counter.add(1, {"item.id": req.item_id, "in_stock": str(in_stock)})
    stock_latency_hist.record((time.time() - start) * 1000, {"item.id": req.item_id})

    return {"item_id": req.item_id, "in_stock": in_stock, "available": available}
