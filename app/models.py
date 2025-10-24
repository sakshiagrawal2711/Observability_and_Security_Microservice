from pydantic import BaseModel
from typing import Optional, List


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionResponse(BaseModel):
    token: str


class LogAnalyzeRequest(BaseModel):
    logs: str


class LogAnalyzeResponse(BaseModel):
    counts: dict
    top_errors: List[str]


class SummaryResponse(BaseModel):
    total_alerts: int
    breakdown: dict
    last_alert_timestamps: List[str]
    avg_last_10_cpu: float
    avg_last_10_memory: float
