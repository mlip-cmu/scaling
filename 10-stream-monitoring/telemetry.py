"""Instrumentation: traces with OpenTelemetry (sent to Jaeger) and metrics for Prometheus."""

import json
import os
import socket

from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram, start_http_server

SECONDS = [0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10, 20, 30, 60]
PROCESSED = Counter("messages_processed", "Messages processed", ["component", "topic"])
FAILED = Counter("messages_failed", "Messages that could not be processed", ["component"])
DURATION = Histogram(
    "processing_seconds", "Time to process a message", ["component"], buckets=SECONDS
)
WAIT = Histogram(
    "queue_wait_seconds",
    "Time from producing to consuming a message",
    ["component"],
    buckets=SECONDS,
)
LAG = Gauge(
    "consumer_lag",
    "Messages in a partition that the group has not read yet",
    ["component", "topic", "partition"],
)


def setup(component: str) -> trace.Tracer:
    """Send traces to the OTLP endpoint (Jaeger) and serve metrics on port 8000."""
    resource = Resource.create(
        {"service.name": component, "service.instance.id": socket.gethostname()[:12]}
    )
    provider = TracerProvider(resource=resource)
    endpoint = os.environ.get("OTLP_ENDPOINT", "http://localhost:4318")
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(f"{endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    start_http_server(8000)
    return trace.get_tracer(component)


def inject() -> list[tuple[str, bytes]]:
    """The context of the current span, as Kafka message headers (W3C traceparent)."""
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return [(k, v.encode()) for k, v in carrier.items()]


def extract(msg):
    """The span context that the producer of this message sent in the headers."""
    return propagate.extract({k: v.decode() for k, v in msg.headers() or []})


def lag_statistics(component: str):
    """A callback for the statistics of the Kafka client: the lag of each assigned partition."""

    def on_stats(stats: str) -> None:
        for topic, t in json.loads(stats).get("topics", {}).items():
            for partition, p in t["partitions"].items():
                if partition != "-1" and p.get("consumer_lag", -1) >= 0:
                    LAG.labels(component, topic, partition).set(p["consumer_lag"])

    return on_stats
