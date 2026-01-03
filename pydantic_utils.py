from __future__ import annotations

import os
from typing import Any


def Field(default: Any = None, default_factory=None):
    return default


class BaseModel:
    def model_dump(self) -> dict:
        return self.__dict__
