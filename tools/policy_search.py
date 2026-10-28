"""Tool: search_student_policy."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent.state import RequestContext, ToolResult
from agent.tool_registry import ToolSpec
from services.container import Services


class PolicySearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")   # unknown/smuggled fields are rejected, not ignored
    query: str = Field(min_length=3, max_length=300, description="The policy question, in the student's own words.")
    top_k: int = Field(default=3, ge=1, le=5)


def make_tool(svc: Services) -> ToolSpec:
    def handler(ctx: RequestContext, args: PolicySearchInput) -> ToolResult:
        res = svc.policy.search(args.query, args.top_k)
        evidence = [h.metadata() for h in res.hits] if res.sufficient else []
        if not res.sufficient:
            return ToolResult(True, data={
                "sufficient": False, "chunks": [],
                "note": "The policy document does not contain enough information to answer this. "
                        "Do not guess; suggest contacting the Student Support Desk."}, evidence=[])
        chunks = [{"chunk_id": h.chunk_id, "document": h.document, "section": f"{h.section_no}. {h.section_title}",
                   "text": h.text, "score": h.score} for h in res.hits]
        return ToolResult(True, data={"sufficient": True, "chunks": chunks,
                                      "note": "Answer only from these chunks and cite the chunk_id."}, evidence=evidence)

    return ToolSpec(
        name="search_student_policy", required_permission="policy:read",
        description="Search the student policy handbook (fees, payment failures, late fees, scholarships, course changes, "
                    "support requests, escalation, privacy). Returns the relevant chunks only.",
        input_model=PolicySearchInput, handler=handler)
