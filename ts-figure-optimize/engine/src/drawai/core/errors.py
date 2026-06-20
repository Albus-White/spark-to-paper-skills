from __future__ import annotations

from typing import Any


class StageFailure(RuntimeError):
    def __init__(
        self,
        stage_id: str,
        message: str,
        *,
        contract: str,
        details: Any = None,
    ) -> None:
        super().__init__(f"{stage_id} failed {contract} contract: {message}")
        self.stage_id = stage_id
        self.contract = contract
        self.details = details
