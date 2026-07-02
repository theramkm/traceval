import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

from traceval.ingest.base import Adapter
from traceval.model import Trace

logger = logging.getLogger(__name__)


class GenericAdapter(Adapter):
    format_name: ClassVar[str] = "generic"

    def detect(self, first_lines: list[str]) -> bool:
        if not first_lines:
            return False
        try:
            data = json.loads(first_lines[0])
            # Check for keys unique to canonical Trace model
            return "trace_id" in data and "steps" in data
        except Exception:
            return False

    def parse(self, path: Path) -> Iterator[Trace]:
        with open(path, encoding="utf-8") as f:
            for line_idx, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    yield Trace.model_validate(data)
                except Exception as e:
                    logger.warning(
                        "Line %d: failed to parse trace. Error: %s",
                        line_idx,
                        str(e),
                    )
