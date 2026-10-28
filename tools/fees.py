"""Tool: get_fee_status (authorization enforced in FeeService, not here and not in the prompt)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from agent.state import RequestContext, ToolResult
from agent.tool_registry import ToolSpec
from services.container import Services


class FeeStatusInput(BaseModel):
    student_id: str | None = Field(default=None, pattern=r"^S\d{4}$",
                                   description="Leave empty. Only the signed-in student's own record can be read.")


def make_tool(svc: Services) -> ToolSpec:
    def handler(ctx: RequestContext, args: FeeStatusInput) -> ToolResult:
        return ToolResult(True, data=svc.fees.get_fee_status(ctx, args.student_id))

    return ToolSpec(
        name="get_fee_status", required_permission="fee:read_own",
        description="Get the fee status (total, paid, outstanding, due date, status) of the signed-in student's own fee record.",
        input_model=FeeStatusInput, handler=handler)
