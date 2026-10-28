"""Tool package: builds the registry of application tools."""
from agent.tool_registry import ToolRegistry
from services.container import Services


def build_registry(svc: Services) -> ToolRegistry:
    from tools import fees, policy_search, scholarships, sensitive_actions, support_requests
    reg = ToolRegistry(
        guard=svc.tool_guard,
        on_tool_error=lambda name, ctx: svc.audit.record("TOOL_EXECUTION_FAILED", ctx=ctx, target_type="tool", target_id=name,
                                                         result="failure", error_category="tool_error"))
    for mod in (fees, scholarships, support_requests, policy_search, sensitive_actions):
        reg.register(mod.make_tool(svc))
    return reg
