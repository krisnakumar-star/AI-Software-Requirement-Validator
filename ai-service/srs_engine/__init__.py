"""ReqValidator local SRS intelligence engine (no external AI services)."""
from .engine import ENGINE_VERSION, analyze_batch, analyze_single, engine_status

__all__ = ["ENGINE_VERSION", "analyze_batch", "analyze_single", "engine_status"]
