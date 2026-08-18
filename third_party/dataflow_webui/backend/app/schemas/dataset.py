from pydantic import BaseModel, Field
from typing import Any, Optional, List, Dict
from app.schemas.pipelines import Pipeline

class DatasetIn(BaseModel):
    name: str
    root: str
    pipeline: str = Field(
        ...,
        description="指定一个或多个该数据集适合的 pipeline"
    )
    # Integration metadata may contain booleans, counts and structured
    # provenance in addition to strings.
    meta: Dict[str, Any] = Field(default_factory=dict)

class DatasetOut(DatasetIn):
    id: str
    num_samples: int = 0
    file_size: int = 0
    hash: Optional[str] = None
