"""Tool: get_scholarship_status."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.state import RequestContext, ToolResult
from agent.tool_registry import ToolSpec
from services.container import Services


class ScholarshipInput(BaseModel):
    student_id: str | None = Field(default=None, pattern=r"^S\d{4}$",
                                   description="Leave empty for the signed-in student's own record.")


def make_tool(svc: Services) -> ToolSpec:
    def handler(ctx: RequestContext, args: ScholarshipInput) -> ToolResult:
        target = args.student_id or ctx.student_id
        if not target:
            return ToolResult(False, error_code="missing_student", user_message="Which student ID should I look up?")
        return ToolResult(True, data=svc.scholarships.get_scholarship_status(target))

    return ToolSpec(
        name="get_scholarship_status",
        description="Get the scholarship application status of the student's own record (scheme, status, amount).",
        input_model=ScholarshipInput, handler=handler)
