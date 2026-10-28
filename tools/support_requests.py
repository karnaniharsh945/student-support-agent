"""Tool: create_support_request."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.state import RequestContext, ToolResult
from agent.tool_registry import ToolSpec
from services.container import Services


class SupportRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")   # unknown/smuggled fields are rejected, not ignored
    category: Literal["FEES", "SCHOLARSHIP", "COURSE_CHANGE", "TECHNICAL", "OTHER"]
    description: str = Field(min_length=10, max_length=500, description="What the student needs help with.")
    priority: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"


def make_tool(svc: Services) -> ToolSpec:
    def handler(ctx: RequestContext, args: SupportRequestInput) -> ToolResult:
        created = svc.support.create(ctx, args.category, args.description, args.priority)
        return ToolResult(True, data=created)

    return ToolSpec(
        name="create_support_request", required_permission="support:create_own",
        description="Create a support ticket for the signed-in student. Only call when the student wants to raise a request "
                    "and has described the issue; ask them for the details first if the description is missing.",
        input_model=SupportRequestInput, handler=handler)
