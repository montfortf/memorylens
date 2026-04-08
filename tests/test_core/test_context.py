from __future__ import annotations

from memorylens._core.context import MemoryContext, get_current_context


class TestMemoryContext:
    def test_context_sets_and_clears(self):
        assert get_current_context() is None
        with MemoryContext(agent_id="bot", session_id="s1", user_id="u1"):
            ctx = get_current_context()
            assert ctx is not None
            assert ctx.agent_id == "bot"
            assert ctx.session_id == "s1"
            assert ctx.user_id == "u1"
        assert get_current_context() is None

    def test_nested_context_overrides(self):
        with MemoryContext(agent_id="outer", session_id="s1", user_id="u1"):
            assert get_current_context().agent_id == "outer"
            with MemoryContext(agent_id="inner", session_id="s2", user_id="u2"):
                assert get_current_context().agent_id == "inner"
                assert get_current_context().session_id == "s2"
            assert get_current_context().agent_id == "outer"

    def test_partial_context(self):
        with MemoryContext(agent_id="bot"):
            ctx = get_current_context()
            assert ctx.agent_id == "bot"
            assert ctx.session_id is None
            assert ctx.user_id is None

    def test_context_outside_block_is_none(self):
        assert get_current_context() is None
