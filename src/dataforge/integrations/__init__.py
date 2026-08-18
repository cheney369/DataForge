"""Adapters for external processing platforms embedded by DataForge."""

from .dataflow import DataFlowAdapter, pipeline_config_hash

__all__ = ["DataFlowAdapter", "pipeline_config_hash"]
