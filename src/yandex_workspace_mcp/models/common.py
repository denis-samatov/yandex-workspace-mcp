from pydantic import BaseModel, ConfigDict
from typing import Literal

class BaseResource(BaseModel):
    model_config = ConfigDict(extra="ignore")
