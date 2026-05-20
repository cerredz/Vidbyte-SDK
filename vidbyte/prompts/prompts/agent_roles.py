from __future__ import annotations


class AgentRolePrompt:
    """Reusable system prompt for a user-defined agent role."""

    def __init__(self, name: str, template: str) -> None:
        self.name = f"agent_role.{name}"
        self.role = name
        self.template = template

    def export(self) -> str:
        return self.template
