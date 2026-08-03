"""
Common OpenTelemetry bootstrap: traces + metrics + logs, all exported via OTLP/gRPC.

Point OTEL_EXPORTER_OTLP_ENDPOINT at your collector, e.g.:
  http://otel-collector.observability.svc.cluster.local:4317

All other behavior (sampling, batching, resource attrs) is controlled by env vars
so you don't need to touch app code to retune it.
"""
import logging
import os

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

from opentelemetry.instrumentation.logging import LoggingInstrumentor


def init_otel(service_name: str):
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    environment = os.getenv("DEPLOY_ENV", "dev")

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": os.getenv("SERVICE_NAMESPACE", "otel-demo"),
            "service.version": os.getenv("SERVICE_VERSION", "0.1.0"),
            "deployment.environment": environment,
        }
    )

    # ---- Traces ----
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # ---- Metrics ----
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
        export_interval_millis=int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "10000")),
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # ---- Logs ----
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=otlp_endpoint, insecure=True))
    )
    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    LoggingInstrumentor().instrument(set_logging_format=True)

    return trace.get_tracer(service_name), metrics.get_meter(service_name)
