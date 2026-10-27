"""Tool package: builds the registry of application tools."""
from agent.tool_registry import ToolRegistry
from services.container import Services


def build_registry(svc: Services) -> ToolRegistry:
    from tools import fees, policy_search, scholarships, support_requests
    reg = ToolRegistry()
    for mod in (fees, scholarships, support_requests, policy_search):
        reg.register(mod.make_tool(svc))
    return reg
