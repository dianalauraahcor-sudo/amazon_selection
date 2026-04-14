from pydantic import BaseModel, Field
from typing import List, Optional


class AnalyzeRequest(BaseModel):
    category: str = Field("", description="Amazon category name or URL")
    asins: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    target_margin: float = Field(0.30, ge=0, le=0.9)
    fee_rate: float = Field(0.30, ge=0, le=0.9)
    excel_filenames: List[str] = Field(default_factory=list, description="Uploaded Excel file references")


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending|running|done|error
    current_node: Optional[str] = None
    progress: int = 0
    error: Optional[str] = None
    report_filename: Optional[str] = None
