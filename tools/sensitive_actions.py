"""Tool: request_course_change - the sensitive action that REQUIRES human approval.

The tool can only *create a pending approval request*. There is deliberately no tool that approves or
executes it: approval happens in the approver UI via ApprovalService.decide(), which the LLM cannot reach.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent.state import RequestContext, ToolResult
from agent.tool_registry import ToolSpec
from services.approvals import ApprovalError
from services.container import Services


class CourseChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")   # unknown/smuggled fields are rejected, not ignored
    new_course: str = Field(min_length=2, max_length=60, description="Course code (e.g. AIML501) or course name.")
    reason: str = Field(default="", max_length=300, description="Why the student wants the change (optional).")


def make_tool(svc: Services) -> ToolSpec:
    def handler(ctx: RequestContext, args: CourseChangeInput) -> ToolResult:
        try:
            r = svc.approvals.request_course_change(ctx, args.new_course, args.reason)
        except ApprovalError as e:
            return ToolResult(False, error_code=e.category, user_message=e.message)
        return ToolResult(True, data={**r, "message": "NOT applied yet. Requires approval by the Academic Office."},
                          approval_state=r["status"])

    return ToolSpec(
        name="request_course_change", required_permission="course_change:request_own",
        description="Submit a request to change the signed-in student's course. This does NOT change the record: it creates "
                    "a pending approval request that an Academic Office approver must approve before anything happens.",
        input_model=CourseChangeInput, handler=handler)
