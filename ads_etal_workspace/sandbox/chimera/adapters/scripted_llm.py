"""Deterministic fake chat model for offline tests: replays a scripted list of assistant turns, including
OpenAI-style tool calls, so AgentExecutor tool loops run without any network.

    llm = ScriptedChatModel(turns=[tool_call("check_business_rules", price_change=-0.9, ad_spend=0),
                                   say('{"action": {"price_change": -0.1, "ad_spend": 300}}')])
A turn may also be a callable `(messages) -> AIMessage` for state-dependent scripts. Running past the end of
the script raises, so a test cannot silently loop.
"""
from __future__ import annotations

import itertools
import json
from typing import Any, Callable, List, Optional, Union

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_ids = itertools.count(1)


def say(text: str) -> AIMessage:
    return AIMessage(content=text)


def tool_call(name: str, **args: Any) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{next(_ids)}", "type": "tool_call"}])


class ScriptedChatModel(BaseChatModel):
    turns: List[Any]
    seen: List[Any] = []          # every message list the model was invoked with (for assertions)
    cursor: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):   # AgentExecutor binds tools; the script already decides the calls
        return self

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, run_manager=None, **kwargs) -> ChatResult:
        if self.cursor >= len(self.turns):
            raise RuntimeError(f"ScriptedChatModel exhausted after {len(self.turns)} turns")
        turn = self.turns[self.cursor]
        self.cursor += 1
        self.seen.append(list(messages))
        msg = turn(messages) if callable(turn) else turn
        return ChatResult(generations=[ChatGeneration(message=msg)])
