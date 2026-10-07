from asago_artifact_generator.extract import extract_scenario
from asago_artifact_generator.garak.classify import lookup_surface

from asago_demo.artifact_context import adapt_context


def context(mode="indirect", source="integration", name="RAG knowledge retrieval response"):
    return extract_scenario(
        {
            "scenario_id": "test",
            "narrative": {"entry_point": name},
            "actor_profile": {
                "access": {
                    "initial_entry_point_id": "ep:1",
                    "ingress_mode": mode,
                    "influence_source_kind": source,
                    "influence_source_id": "int:1",
                    "trust_boundary_id": "tb:1",
                }
            },
            "projection": {
                "canonical_ingress": {"entry_point_id": "ep:1"},
                "capability_snapshot": {
                    "profile": {
                        "entry_points": [
                            {
                                "entry_point_id": "ep:1",
                                "name": name,
                                "controllability": mode,
                                "entry_point_type": "external_content",
                            }
                        ]
                    }
                },
            },
        }
    )


def test_indirect_retrieval_maps_to_tool_transport_without_rewriting_scenario():
    original = context()
    adapted = adapt_context(original)
    assert lookup_surface(adapted) == "tool_return"
    assert adapted.raw is original.raw
    assert original.entry_point == "RAG knowledge retrieval response"
    assert adapted.behavior_spec == original.behavior_spec


def test_direct_or_unrecognized_content_keeps_existing_classification():
    for original in (
        context(mode="direct"),
        context(source="unknown"),
        context(name="Other content"),
    ):
        assert adapt_context(original) is original
        assert lookup_surface(original) == "user_turn"
