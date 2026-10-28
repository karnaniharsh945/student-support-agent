"""Tool: get_scholarship_status."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.state import RequestContext, ToolResult
from agent.tool_registry import ToolSpec
from services.container import Services


class ScholarshipInput(BaseModel):
    student_id: str | None = Field(default=None, pattern=r"^S\d{4}$",
                                   description="Leave empty. Only the signed-in student's own record can be read.")


def make_tool(svc: Services) -> ToolSpec:
    def handler(ctx: RequestContext, args: ScholarshipInput) -> ToolResult:
        return ToolResult(True, data=svc.scholarships.get_scholarship_status(ctx, args.student_id))

    return ToolSpec(
        name="get_scholarship_status", required_permission="scholarship:read_own",
        description="Get the scholarship application status of the signed-in student's own record (scheme, status, amount).",
        input_model=ScholarshipInput, handler=handler)
