"""skill-stats — per-skill usage counters for Hermes Agent.

Every ``skill_view`` load increments a counter for that skill, in two views:
global (all-time) and per-session (which skills this session used most).
See ``skill_stats_store`` (persistence), ``skill_stats_hooks`` (counting +
slash command) and ``skill_stats_cli`` (``hermes skill-stats``).

Wiring goes only through the public plugin API.
"""

from __future__ import annotations

from . import skill_stats_cli, skill_stats_hooks

HOOKS = ("pre_tool_call", "on_session_start", "on_session_end")


def register(ctx) -> None:
    """Plugin entry point — called by the Hermes plugin loader."""
    ctx.register_hook("pre_tool_call", skill_stats_hooks.on_pre_tool_call)
    ctx.register_hook("on_session_start", skill_stats_hooks.on_session_start)
    ctx.register_hook("on_session_end", skill_stats_hooks.on_session_end)
    ctx.register_command(
        "skill-stats", skill_stats_hooks.on_skill_stats,
        description="This session's skill usage: /skill-stats [--json] · global: /skill-stats global · reset session: /skill-stats reset",
        args_hint="[global] [--json]",
    )
    ctx.register_cli_command(
        "skill-stats",
        "Per-skill usage statistics — bare call shows global; /skill-stats shows this session",
        skill_stats_cli.setup_cli,
        skill_stats_cli.handle_cli,
    )
    ctx.register_system_prompt_section(
        "skill-stats",
        "Skill usage is counted by the skill-stats plugin. "
        "Run /skill-stats for this session's most-used skills, or /skill-stats global for all-time totals.",
        position="after_memory", max_chars=400,
    )


__all__ = ["register"]
