"""register(ctx) wiring: hooks, /skill-stats and `hermes skill-stats` go through the public plugin API."""

from __future__ import annotations

import argparse

import pytest

import skill_stats_plugin
from skill_stats_plugin import skill_stats_hooks


class RecordingCtx:
    def __init__(self):
        self.hooks, self.commands, self.cli, self.sections = [], [], [], []

    def register_hook(self, name, callback, **kwargs):
        self.hooks.append((name, callback))

    def register_command(self, name, handler, **kwargs):
        self.commands.append((name, handler, kwargs))

    def register_cli_command(self, name, help, setup_fn, handler_fn, **kwargs):
        self.cli.append((name, help, setup_fn, handler_fn))

    def register_system_prompt_section(self, id, content, **kwargs):
        self.sections.append((id, content, kwargs))


@pytest.fixture
def ctx():
    c = RecordingCtx()
    skill_stats_plugin.register(c)
    return c


def test_registers_three_hooks(ctx):
    assert dict(ctx.hooks) == {
        "pre_tool_call": skill_stats_hooks.on_pre_tool_call,
        "on_session_start": skill_stats_hooks.on_session_start,
        "on_session_end": skill_stats_hooks.on_session_end,
    }


def test_registers_skill_stats_command(ctx):
    (name, handler, kwargs), = ctx.commands
    assert name == "skill-stats"
    assert handler is skill_stats_hooks.on_skill_stats
    assert kwargs["args_hint"] == "[global] [--json] [--day N] [--offset N] [--limit N] [--group]"


def test_registers_skill_stats_cli(ctx):
    (name, help_text, setup_fn, handler_fn), = ctx.cli
    assert name == "skill-stats"
    parser = argparse.ArgumentParser()
    setup_fn(parser)
    assert parser.parse_args([]).scope == "global"  # bare call = global
    assert parser.parse_args(["reset"]).subcommand == "reset"
    assert parser.parse_args(["doctor"]).subcommand == "doctor"


def test_registers_prompt_section(ctx):
    (section_id, content, kwargs), = ctx.sections
    assert section_id == "skill-stats"
    assert "/skill-stats" in content
