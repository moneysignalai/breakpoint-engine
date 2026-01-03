from __future__ import annotations

import os
from typing import Any, Dict

from pydantic import BaseModel


class SettingsConfigDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class BaseSettings(BaseModel):
    def __init__(self, **kwargs: Any):
        for key, value in self.__class__.__annotations__.items():
            env_key = key
            env_val = os.environ.get(env_key)
            if env_val is not None:
                try:
                    if value is bool:
                        env_val = env_val.lower() in {"1", "true", "yes", "on"}
                    elif value is int:
                        env_val = int(env_val)
                    elif value is float:
                        env_val = float(env_val)
                except Exception:
                    pass
                setattr(self, key, env_val)
            elif key in kwargs:
                setattr(self, key, kwargs[key])
            elif hasattr(self, key):
                pass
            else:
                default_val = getattr(self.__class__, key, None)
                setattr(self, key, default_val)

    def model_dump(self) -> Dict[str, Any]:
        return self.__dict__.copy()
