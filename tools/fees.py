"""Tool: get_fee_status."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.state import RequestContext, ToolResult
from agent.tool_registry import ToolSpec
from services.container import Services


class FeeStatusInput(BaseModel):
    student_id: str | None = Field(default=None, pattern=r"^S\d{4}$",
                                   description="Leave empty for the signed-in student's own record.")


def make_tool(svc: Services) -> ToolSpec:
    def handler(ctx: RequestContext, args: FeeStatusInput) -> ToolResult:
        target = args.student_id or ctx.student_id
        if not target:
            return ToolResult(False, error_code="missing_student", user_message="Which student ID should I look up?")
        return ToolResult(True, data=svc.fees.get_fee_status(target))

    return ToolSpec(
        name="get_fee_status",
        description="Get the fee status (total, paid, outstanding, due date, status) of the student's own fee record.",
        input_model=FeeStatusInput, handler=handler)
