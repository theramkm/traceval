from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar, Protocol

from traceval.model import Trace


class Adapter(Protocol):
    format_name: ClassVar[str]

    def __init__(self, tool_span_globs: list[str] | None = None) -> None: ...

    def detect(self, first_lines: list[str]) -> bool: ...

    def parse(self, path: Path) -> Iterator[Trace]: ...
