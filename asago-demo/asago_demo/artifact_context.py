"""Map the declared retrieval carrier to the pinned generator's legacy surface tag.

Scenario Generator records the consuming zone (reasoning). Artifact Generator
PR #8 instead uses a parenthetical transport tag to pick the chat role. Keep
those distinct: only adapt the in-memory artifact input, never the admitted YAML.
"""

from dataclasses import replace


def adapt_context(ctx):
    access = ctx.raw.get("actor_profile", {}).get("access", {})
    projection = ctx.raw.get("projection", {})
    ingress = projection.get("canonical_ingress", {}).get("entry_point_id")
    entries = projection.get("capability_snapshot", {}).get("profile", {}).get("entry_points", [])
    declared_retrieval = any(
        entry.get("entry_point_id") == ingress
        and entry.get("name") == ctx.entry_point == "RAG knowledge retrieval response"
        and entry.get("controllability") == "indirect"
        and entry.get("entry_point_type") == "external_content"
        for entry in entries
    )
    if (
        declared_retrieval
        and access.get("initial_entry_point_id") == ingress
        and access.get("ingress_mode") == "indirect"
        and access.get("influence_source_kind") == "integration"
        and access.get("influence_source_id")
        and access.get("trust_boundary_id")
    ):
        return replace(ctx, entry_point=ctx.entry_point + " (tool_execution)")
    return ctx
