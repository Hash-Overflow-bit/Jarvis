"""
core/logging/tracing.py
========================
OpenTelemetry tracing initialization.
Instruments CrewAI and LangChain loops and exports spans
to Arize Phoenix using standard HTTP OTLP protocols.
"""

import logging
from core.config import settings

logger = logging.getLogger("jarvis_tracing")


def init_telemetry():
    """
    Initializes OpenTelemetry and instruments CrewAI/LangChain loops
    to export execution traces to Arize Phoenix.
    """
    if not settings.telemetry_enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from openinference.instrumentation.crewai import CrewAIInstrumentor
        from openinference.instrumentation.langchain import LangChainInstrumentor

        # Configure the OTel trace provider
        provider = TracerProvider()

        # Configure standard HTTP OTLP trace exporter (targeting Arize Phoenix receiver)
        endpoint = settings.otel_exporter_otlp_endpoint
        logger.info(f"Initializing OpenTelemetry. Exporting traces to OTLP endpoint: {endpoint}")

        exporter = OTLPSpanExporter(endpoint=endpoint)
        processor = SimpleSpanProcessor(exporter)
        provider.add_span_processor(processor)

        # Register the provider globally
        trace.set_tracer_provider(provider)

        # Auto-instrument CrewAI multi-agent frameworks
        CrewAIInstrumentor().instrument()

        # Auto-instrument LangChain & LangGraph agents
        LangChainInstrumentor().instrument()

        logger.info("Telemetry tracing successfully initialized (OTLP -> Arize Phoenix).")
    except Exception as e:
        logger.warning(f"Telemetry initialization failed: {e}")
