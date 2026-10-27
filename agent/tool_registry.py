"""Tool registry: schema export, argument validation and guarded execution.

The model may *propose* a tool call; this module decides whether and how it executes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from agent.state import RequestContext, ToolCallRecord, ToolResult
from services.records import RecordNotFound


@dataclass
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[RequestContext, BaseModel], ToolResult]

    def openai_schema(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                  "parameters": schema}}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.openai_schema() for t in self._tools.values()]

    def execute(self, name: str, raw_args: Any, ctx: RequestContext) -> tuple[ToolResult, ToolCallRecord]:
        started = time.perf_counter()
        args_for_trace = raw_args if isinstance(raw_args, dict) else {"_raw": str(raw_args)[:200]}
        result = self._run(name, raw_args, ctx)
        rec = ToolCallRecord(name=name, arguments=args_for_trace, ok=result.ok, error_code=result.error_code,
                             latency_ms=round((time.perf_counter() - started) * 1000, 2))
        return result, rec

    def _run(self, name: str, raw_args: Any, ctx: RequestContext) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(False, error_code="unknown_tool", user_message="That action is not available.")
        if not isinstance(raw_args, dict):
            return ToolResult(False, error_code="invalid_arguments", user_message="The tool arguments were malformed.")
        try:
            args = spec.input_model.model_validate(raw_args)
        except ValidationError as exc:
            fields = ", ".join(sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]})) or "arguments"
            return ToolResult(False, error_code="invalid_arguments",
                              user_message=f"Some required details are missing or invalid: {fields}.")
        try:
            return spec.handler(ctx, args)
        except RecordNotFound:
            return ToolResult(False, error_code="not_found", user_message="No matching record was found.")
        except Exception:  # never leak stack traces / internals to the model or user
            return ToolResult(False, error_code="tool_error",
                              user_message="A system error occurred while running this action. Please try again later.")
