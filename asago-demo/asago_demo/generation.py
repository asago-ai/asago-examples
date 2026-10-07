"""Scoped compatibility fixes for the demo's pinned Scenario Generator.

These only guide model responses. Upstream parsing, qualification and admission
remain authoritative; no generated actors or rejected results are rewritten.
Each demo stage runs in its own process, so temporary patches cannot affect
another run. Remove this bridge when the pinned dependency incorporates fixes.
"""

import inspect
import json
import threading
import time
from contextlib import ExitStack, contextmanager
from functools import wraps
from unittest.mock import patch


class RequestPacer:
    """Share request-start spacing across the pipeline's concurrent clients."""

    def __init__(self, interval, *, clock=time.monotonic, sleep=time.sleep):
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self.lock = threading.Lock()
        self.next_start = 0.0

    def wait(self):
        with self.lock:
            delay = max(0, self.next_start - self.clock())
            if delay:
                self.sleep(delay)
            self.next_start = self.clock() + self.interval


@contextmanager
def generation_compatibility(*, provider: str, demo_preset: bool):
    from asago_scenario_generator.llm.client import LLMClient
    from asago_scenario_generator.pipeline.generate import actor, behavior_semantics, tree

    original_prompt = actor._actor_draft_prompt
    original_model = behavior_semantics.build_behavior_draft_response_model
    original_tree_prompt = tree._semantic_user_prompt
    original_complete = LLMClient.complete
    complete_signature = inspect.signature(original_complete)
    pacer = RequestPacer(4.2)
    local_request_lock = threading.Lock()

    @wraps(original_complete)
    def paced_complete(client, *args, **kwargs):
        if provider == "google" and client.model == "gemini-3.1-flash-lite":
            pacer.wait()
        call = complete_signature.bind(client, *args, **kwargs)
        response_model = call.arguments.get("response_format")
        if getattr(response_model, "__name__", "").startswith("FilterMapDraftV3For"):
            call.arguments["user_prompt"] += (
                "\nKeep each candidate rationale to one short sentence, at most 220 "
                "characters including spaces (the schema permits at most 240)."
            )
        if provider == "ollama":
            # Local inference queues can make concurrent requests time out before
            # they begin. Each request gets its own timeout after acquiring this lock.
            with local_request_lock:
                return original_complete(*call.args, **call.kwargs)
        return original_complete(*call.args, **call.kwargs)

    @wraps(original_tree_prompt)
    def ordered_tree(use_case, seed, narrative, inventory, consistency_feedback):
        prompt = original_tree_prompt(use_case, seed, narrative, inventory, consistency_feedback)
        handles = [leaf["handle"] for leaf in inventory]
        return prompt + (
            "\nFor this demo use one group. Copy this exact ordered list into its "
            f"leaf_handles: {json.dumps(handles)}. Do not sort, repeat or omit handles. "
            "Author the root/group labels and descriptions to explain this attack.\n"
        )

    @wraps(original_prompt)
    def concise_actor(*args, **kwargs):
        suffix = (
            "\nUse 1-2 short sentences per belief, desire, or intention. Each list item MUST "
            "be at most 180 characters, including spaces. Keep rationale under 300 characters."
        )
        if demo_preset:
            suffix += (
                " For this multi-step demo, choose an advanced-capability actor from the "
                "compatible actor/capability choices when one is available. Use that exact "
                "actor_choice_handle and ground the actor motivation in the selected attack. "
                "Do not invent access or resources."
            )
        return original_prompt(*args, **kwargs) + suffix

    @wraps(original_model)
    def bounded_behavior(handles, **kwargs):
        handles = tuple(handles)
        base = original_model(handles, **kwargs)
        if not 1 <= len(handles) <= 64:
            raise ValueError("Behavior handle count is outside the tested Google demo schema")

        def schema(cls, *args, **kw):
            body = base.model_json_schema(*args, **kw)
            groups = body["properties"]["scenarios"]
            steps = body["$defs"]["BehaviorScenarioDraft"]["properties"]["steps"]
            if groups.get("maxItems") != 8 or steps.get("maxItems") != 64:
                raise ValueError("Scenario Generator schema changed; update the demo adapter")
            # Google rejects the original 8 x 64 nested schema. One group can
            # contain every selected action/assertion exactly once. The original
            # Pydantic model and behavior compiler still validate the response.
            groups["maxItems"] = 1
            steps["maxItems"] = len(handles)
            return body

        return type(base.__name__, (base,), {"model_json_schema": classmethod(schema)})

    with ExitStack() as stack:
        stack.enter_context(patch.object(actor, "_actor_draft_prompt", concise_actor))
        if demo_preset:
            stack.enter_context(patch.object(tree, "_semantic_user_prompt", ordered_tree))
        if demo_preset or provider == "ollama":
            stack.enter_context(patch.object(LLMClient, "complete", paced_complete))
        if provider == "google":
            stack.enter_context(
                patch.object(
                    behavior_semantics, "build_behavior_draft_response_model", bounded_behavior
                )
            )
        yield
