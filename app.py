# app.py

import time
import random
import logging
import os
from flask import Flask, request, jsonify
import threading
import requests

# OpenTelemetry imports
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
import opentelemetry.instrumentation.requests

# Create log directory
os.makedirs("./tmp/app_logs", exist_ok=True)

# Configure logging for Loki
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("./tmp/app_logs/app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("grafana-lgtm-test")

# Create Flask app
app = Flask(__name__)

# Configure OpenTelemetry
def configure_opentelemetry():
    # Configure common resource for all telemetry data
    resource = Resource.create({
        "service.name": "grafana-lgtm-test",
        "service.version": "0.1.0",
        "deployment.environment": "local-test"
    })
    
    # Configure tracing
    trace_provider = TracerProvider(resource=resource)
    otlp_trace_exporter = OTLPSpanExporter(
        endpoint="localhost:5555",  # Using port 5555
        insecure=True
    )
    span_processor = BatchSpanProcessor(otlp_trace_exporter)
    trace_provider.add_span_processor(span_processor)
    trace.set_tracer_provider(trace_provider)
    
    # Configure metrics
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint="localhost:5555",  # Using port 5555
            insecure=True
        ),
        export_interval_millis=5000
    )
    metrics_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(metrics_provider)
    
    # Instrument Flask
    FlaskInstrumentor().instrument_app(app)
    
    # Instrument logging for correlation with traces
    LoggingInstrumentor().instrument(set_logging_format=True)
    
    # Instrument HTTP requests
    RequestsInstrumentor().instrument()
    
    return trace.get_tracer(__name__), metrics.get_meter(__name__)

tracer, meter = configure_opentelemetry()

# Create some metrics
request_counter = meter.create_counter(
    name="http_requests_total",
    description="Total number of HTTP requests",
    unit="1"
)

request_duration = meter.create_histogram(
    name="http_request_duration_seconds",
    description="HTTP request duration in seconds",
    unit="s"
)

process_memory_gauge = meter.create_up_down_counter(
    name="process_memory_usage",
    description="Memory usage of the process",
    unit="bytes"
)

# Routes to generate telemetry data
@app.route('/')
def home():
    with tracer.start_as_current_span("home_endpoint"):
        logger.info("Home endpoint accessed")
        request_counter.add(1, {"endpoint": "home", "method": "GET"})
        time.sleep(random.uniform(0.01, 0.05))  # Simulate processing time
        return "Hello from Grafana LGTM Test App!"

@app.route('/api/users')
def users():
    with tracer.start_as_current_span("list_users") as span:
        start_time = time.time()
        
        # Simulate DB query with a child span
        with tracer.start_as_current_span("db_query") as child_span:
            child_span.set_attribute("db.name", "user_database")
            child_span.set_attribute("db.query", "SELECT * FROM users")
            time.sleep(random.uniform(0.05, 0.2))  # Simulate DB query time
            
            # Sometimes add an error
            if random.random() < 0.1:
                logger.error("Database timeout while fetching users")
                child_span.set_status(trace.Status(trace.StatusCode.ERROR))
                
        duration = time.time() - start_time
        request_counter.add(1, {"endpoint": "users", "method": "GET"})
        request_duration.record(duration, {"endpoint": "users"})
        
        logger.info(f"Users API call completed in {duration:.4f} seconds")
        return jsonify({"users": ["user1", "user2", "user3"]})

@app.route('/api/items')
def items():
    with tracer.start_as_current_span("list_items") as span:
        start_time = time.time()
        
        # Set some example attributes
        span.set_attribute("http.method", "GET")
        span.set_attribute("http.route", "/api/items")
        
        # Make a nested HTTP call to demonstrate distributed tracing
        try:
            with tracer.start_as_current_span("fetch_details"):
                # This call will be traced and connected to the parent span
                response = requests.get("https://jsonplaceholder.typicode.com/posts/1")
                if response.status_code != 200:
                    logger.warning(f"External API returned status {response.status_code}")
        except Exception as e:
            logger.error(f"Error calling external API: {e}")
        
        # Simulate processing
        time.sleep(random.uniform(0.03, 0.3))
        
        duration = time.time() - start_time
        request_counter.add(1, {"endpoint": "items", "method": "GET"})
        request_duration.record(duration, {"endpoint": "items"})
        
        # Log with different levels
        if duration > 0.2:
            logger.warning(f"Slow items API call: {duration:.4f} seconds")
        else:
            logger.info(f"Items API call completed in {duration:.4f} seconds")
            
        return jsonify({"items": ["item1", "item2", "item3", "item4"]})

@app.route('/api/error')
def error():
    with tracer.start_as_current_span("error_endpoint") as span:
        logger.error("Error endpoint accessed deliberately")
        span.set_status(trace.Status(trace.StatusCode.ERROR, "Deliberate error for testing"))
        request_counter.add(1, {"endpoint": "error", "method": "GET", "status": "error"})
        return jsonify({"error": "This is a test error"}), 500

# Background task to generate periodic metrics and logs
def background_metrics():
    while True:
        # Generate some random memory usage metrics
        memory_usage = random.randint(50 * 1024 * 1024, 200 * 1024 * 1024)  # 50-200 MB
        process_memory_gauge.add(random.randint(-10 * 1024 * 1024, 10 * 1024 * 1024), 
                                {"component": "app_server"})
        
        # Generate some logs
        log_types = ["INFO", "WARNING", "ERROR"]
        weights = [0.7, 0.2, 0.1]
        log_type = random.choices(log_types, weights=weights)[0]
        
        if log_type == "INFO":
            logger.info(f"System running normally. Current memory usage: {memory_usage / (1024*1024):.2f} MB")
        elif log_type == "WARNING":
            logger.warning(f"High memory usage detected: {memory_usage / (1024*1024):.2f} MB")
        else:
            logger.error(f"System resource critical! Memory: {memory_usage / (1024*1024):.2f} MB")
            
        time.sleep(2)  # Generate metrics every 2 seconds

# Health check endpoint
@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "grafana-lgtm-test"})

if __name__ == '__main__':
    # Start background metrics in a separate thread
    metrics_thread = threading.Thread(target=background_metrics, daemon=True)
    metrics_thread.start()
    
    # Start the Flask app
    logger.info("Starting Grafana LGTM test application")
    app.run(host='0.0.0.0', port=8080, debug=True)