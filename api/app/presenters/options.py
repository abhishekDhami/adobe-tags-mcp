from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ViewDepth = Literal["index", "detail", "context", "full"]

DEFAULT_CODE_PREVIEW = 500


@dataclass(frozen=True, slots=True)
class ViewOptions:
    depth: ViewDepth = "detail"
    include_code: bool = False
    include_raw_settings: bool = False
    max_code_length: int = DEFAULT_CODE_PREVIEW

    @property
    def include_logic(self) -> bool:
        return self.depth in {"context", "full"}

    @property
    def include_full_content(self) -> bool:
        return self.depth == "full" or self.include_code
