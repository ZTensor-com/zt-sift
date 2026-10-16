"""Presidio + spaCy en_core_web_sm + the project's custom recognizers."""
from .detector import collapse_overlaps, detect, load_analyzer

__all__ = ["collapse_overlaps", "detect", "load_analyzer"]
