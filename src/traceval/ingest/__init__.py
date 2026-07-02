import logging
from pathlib import Path

from traceval.ingest.base import Adapter
from traceval.ingest.generic import GenericAdapter
from traceval.ingest.langfuse import LangfuseAdapter
from traceval.ingest.langsmith import LangsmithAdapter
from traceval.ingest.otel import OtelAdapter
from traceval.store import TraceStore

ADAPTERS: list[type[Adapter]] = [
    GenericAdapter,
    OtelAdapter,
    LangfuseAdapter,
    LangsmithAdapter,
]


def detect_format(path: Path) -> str:
    first_lines: list[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            for _ in range(5):
                line = f.readline()
                if not line:
                    break
                first_lines.append(line)
    except Exception:
        pass

    for adapter_cls in ADAPTERS:
        adapter = adapter_cls()
        if adapter.detect(first_lines):
            return adapter.format_name
    return "generic"


class WarningCounterHandler(logging.Handler):
    def __init__(self, log_file: Path) -> None:
        super().__init__()
        self.count = 0
        self.log_file = log_file
        # Ensure parent directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        # Clear/initialize the log file
        self.log_file.write_text("", encoding="utf-8")

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.WARNING:
            self.count += 1
        msg = self.format(record)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(msg + "\n")


def ingest_file(
    path: Path,
    store: TraceStore,
    format_name: str = "auto",
    log_path: Path | None = None,
) -> tuple[int, int, int, Path]:
    if format_name == "auto":
        format_name = detect_format(path)

    adapter_cls = next((a for a in ADAPTERS if a.format_name == format_name), None)
    if not adapter_cls:
        raise ValueError(f"Unknown format: {format_name}")

    adapter = adapter_cls()

    if log_path is None:
        log_path = Path("ingest.log")

    # Set up custom logger to count and log warnings
    logger = logging.getLogger("traceval.ingest")
    # Prevent propagation to avoid polluting stdout during runs
    logger.propagate = False
    logger.setLevel(logging.WARNING)

    handler = WarningCounterHandler(log_path)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

    ok_count = 0
    span_count = 0
    try:
        for trace in adapter.parse(path):
            try:
                store.save_trace(trace)
                ok_count += 1
                span_count += len(trace.steps)
            except Exception as e:
                logger.warning("Failed to save trace to DB: %s", str(e))
    finally:
        logger.removeHandler(handler)
        handler.close()

    return ok_count, span_count, handler.count, log_path
