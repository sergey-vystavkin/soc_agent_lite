from prometheus_client import Counter, Histogram

# Custom metrics
webhook_incoming_counter = Counter(
    "webhook_incoming_total",
    "Count of incoming webhook events received",
    labelnames=("endpoint",),
)

workflow_duration_seconds = Histogram(
    "workflow_duration_seconds",
    "Time taken to execute the incident workflow",
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600),
)
