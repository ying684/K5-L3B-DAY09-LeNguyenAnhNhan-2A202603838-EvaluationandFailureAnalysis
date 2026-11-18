"""Four shapes, one function signature."""

from lab8.shapes import orchestrator, single, swarm_reference, workflow

SHAPES = {
    "workflow": workflow.run_claim,
    "single": single.run_claim,
    "orchestrator": orchestrator.run_claim,
    "swarm": swarm_reference.run_claim,
}
