import logging
import os
import uuid
from concurrent import futures

import grpc
import requests

from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.instrumentation.requests import RequestsInstrumentor

from otel_setup import init_otel
import orders_pb2
import orders_pb2_grpc

SERVICE_NAME = "orders"
tracer, meter = init_otel(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)

GrpcInstrumentorServer().instrument()
RequestsInstrumentor().instrument()

INVENTORY_URL = os.getenv("INVENTORY_URL", "http://inventory:8081")

orders_created_counter = meter.create_counter(
    "orders.created", description="Number of orders created"
)
orders_rejected_counter = meter.create_counter(
    "orders.rejected", description="Number of orders rejected due to stock"
)


class OrderServiceServicer(orders_pb2_grpc.OrderServiceServicer):
    def CreateOrder(self, request, context):
        with tracer.start_as_current_span("create-order") as span:
            span.set_attribute("order.item_id", request.item_id)
            span.set_attribute("order.quantity", request.quantity)

            try:
                resp = requests.post(
                    f"{INVENTORY_URL}/check-stock",
                    json={"item_id": request.item_id, "quantity": request.quantity},
                    timeout=5,
                )
                resp.raise_for_status()
                stock = resp.json()
            except requests.RequestException as e:
                logger.error("inventory call failed: %s", e)
                span.record_exception(e)
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                context.set_details("inventory service unavailable")
                return orders_pb2.CreateOrderResponse(
                    order_id="", status="ERROR", in_stock=False
                )

            in_stock = stock.get("in_stock", False)
            order_id = str(uuid.uuid4())

            if in_stock:
                status = "CONFIRMED"
                orders_created_counter.add(1, {"item.id": request.item_id})
                logger.info("order confirmed order_id=%s item=%s", order_id, request.item_id)
            else:
                status = "REJECTED"
                orders_rejected_counter.add(1, {"item.id": request.item_id})
                logger.info("order rejected (out of stock) item=%s", request.item_id)

            span.set_attribute("order.id", order_id)
            span.set_attribute("order.status", status)

            return orders_pb2.CreateOrderResponse(
                order_id=order_id, status=status, in_stock=in_stock
            )


def serve():
    port = os.getenv("GRPC_PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    orders_pb2_grpc.add_OrderServiceServicer_to_server(OrderServiceServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    logger.info("orders gRPC server starting on port %s", port)
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
