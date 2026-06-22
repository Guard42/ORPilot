"""Claude Code-native LLM Strategy Layer — 3 model tier architectures.

Since OR-Copilot is a Claude Code plugin, model selection is modeled directly
after Claude Code's tiered architecture. We do NOT build generic multi-provider
routing — we use Claude Code's native Agent tool for sub-agent delegation with
different model tiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Model Tier (mirrors Claude Code's native tiers)
# ---------------------------------------------------------------------------

class ModelTier(str, Enum):
    """Claude Code native model capability tiers."""
    HAIKU = "haiku"       # Fast, lightweight — classification, KB retrieval, syntax checks
    SONNET = "sonnet"     # Balanced — code generation, verification, reports
    OPUS = "opus"         # Most capable — interview, extraction, formulation, complex reasoning
    MAIN = "main"         # User-selected primary model (pipeline backbone)


# ---------------------------------------------------------------------------
# Architecture Modes
# ---------------------------------------------------------------------------

class ArchitectureMode(str, Enum):
    """Three LLM architectures for OR-Copilot.

    A — Single Model: All tasks use user-selected model. Simplest, lowest cost.
    B — Main + Sub-Agent Secondary: Pipeline backbone uses MAIN tier,
        sub-agents use HAIKU/SONNET for efficiency.
    C — Full Tiered: Claude Code native 4-tier routing.
    """
    A_SINGLE = "A"
    B_MAIN_PLUS_SUB = "B"
    C_FULL_TIERED = "C"


# ---------------------------------------------------------------------------
# Agent → Tier Mapping
# ---------------------------------------------------------------------------

# Architecture C: full Claude Code native 4-tier routing
AGENT_TIER_MAP_C: dict[str, ModelTier] = {
    "or-interviewer":   ModelTier.MAIN,    # Needs deep conversational understanding
    "or-classifier":    ModelTier.HAIKU,   # Lightweight classification
    "or-solver-fit":    ModelTier.SONNET,  # Needs analytical capability
    "or-extractor":     ModelTier.MAIN,    # Structured extraction needs precision
    "or-formulator":    ModelTier.OPUS,    # Mathematical formulation — most critical
    "or-coder":         ModelTier.SONNET,  # Code gen — speed preferred
    "or-verifier":      ModelTier.HAIKU,   # Verification rules are well-defined
    "or-reporter":      ModelTier.SONNET,  # Reports need readability
}

# Architecture B: main pipeline uses MAIN, sub-agents use HAIKU/SONNET
AGENT_TIER_MAP_B: dict[str, ModelTier] = {
    "or-interviewer":   ModelTier.MAIN,
    "or-classifier":    ModelTier.HAIKU,
    "or-solver-fit":    ModelTier.HAIKU,
    "or-extractor":     ModelTier.MAIN,
    "or-formulator":    ModelTier.MAIN,
    "or-coder":         ModelTier.SONNET,
    "or-verifier":      ModelTier.SONNET,
    "or-reporter":      ModelTier.SONNET,
}

# Architecture A: all agents use MAIN tier (user-selected model)
AGENT_TIER_MAP_A: dict[str, ModelTier] = {
    agent: ModelTier.MAIN for agent in AGENT_TIER_MAP_C
}


# ---------------------------------------------------------------------------
# Strategy Configuration
# ---------------------------------------------------------------------------

@dataclass
class LLMStrategyConfig:
    """Configuration for the LLM strategy layer."""
    architecture: ArchitectureMode = ArchitectureMode.B_MAIN_PLUS_SUB
    main_model: Optional[str] = None   # e.g., "claude-sonnet-4-6"
    haiku_model: str = "claude-haiku-4-5"
    sonnet_model: str = "claude-sonnet-4-6"
    opus_model: str = "claude-opus-4-6"


class LLMStrategy:
    """Resolves which model tier should be used for a given agent.

    Since OR-Copilot is a Claude Code plugin, model tier assignment controls
    which model the Claude Code runtime uses when dispatching an Agent tool call.
    The actual API call is handled by Claude Code, not by OR-Copilot directly.
    """

    def __init__(self, config: LLMStrategyConfig | None = None):
        self.config = config or LLMStrategyConfig()
        self._tier_map = self._build_tier_map()

    def _build_tier_map(self) -> dict[str, ModelTier]:
        if self.config.architecture == ArchitectureMode.A_SINGLE:
            return dict(AGENT_TIER_MAP_A)
        elif self.config.architecture == ArchitectureMode.C_FULL_TIERED:
            return dict(AGENT_TIER_MAP_C)
        else:  # B — default
            return dict(AGENT_TIER_MAP_B)

    def get_tier(self, agent_name: str) -> ModelTier:
        """Get the recommended model tier for an agent.

        Returns MAIN if the agent is unknown (safe default).
        """
        return self._tier_map.get(agent_name, ModelTier.MAIN)

    def get_model_name(self, agent_name: str) -> str:
        """Get the specific model name for an agent based on its tier."""
        tier = self.get_tier(agent_name)
        return self._tier_to_model(tier)

    def _tier_to_model(self, tier: ModelTier) -> str:
        if tier == ModelTier.HAIKU:
            return self.config.haiku_model
        elif tier == ModelTier.SONNET:
            return self.config.sonnet_model
        elif tier == ModelTier.OPUS:
            return self.config.opus_model
        else:  # MAIN
            return self.config.main_model or self.config.sonnet_model

    @staticmethod
    def get_architecture_description(mode: ArchitectureMode) -> str:
        """Human-readable description of each architecture."""
        descriptions = {
            ArchitectureMode.A_SINGLE:
                "All tasks use your selected model. Simplest setup, lowest cost, "
                "best for well-defined problems where precision is not critical.",
            ArchitectureMode.B_MAIN_PLUS_SUB:
                "Pipeline backbone uses your main model. Lightweight sub-agents "
                "(classification, verification) use Haiku. Code generation and "
                "reporting use Sonnet. Best balance of quality and cost.",
            ArchitectureMode.C_FULL_TIERED:
                "Full Claude Code native 4-tier routing: Haiku for classification/"
                "verification, Sonnet for code/reports, Opus for formulation, "
                "and your main model for the pipeline backbone. Best quality.",
        }
        return descriptions[mode]


# ---------------------------------------------------------------------------
# Agent delegation helpers (Claude Code-native)
# ---------------------------------------------------------------------------

def build_agent_delegation_prompt(
    agent_name: str,
    agent_description: str,
    input_context: str,
) -> str:
    """Build a prompt for delegating work to a Claude Code sub-agent.

    This prompt is used by the main pipeline orchestrator to dispatch work
    to the specialized agents defined in orpilot/plugin/agents/.
    """
    return f"""You are delegating to the `{agent_name}` sub-agent.

**Agent Role**: {agent_description}

**Context**:
{input_context}

**Instructions**: Call the `{agent_name}` agent to process this task.
The agent will produce structured output according to its specification.
After the agent completes, review the output before proceeding."""


def get_pipeline_agents_for_architecture(mode: ArchitectureMode) -> list[str]:
    """Get the ordered list of agents for the pipeline based on architecture.

    All architectures use the same agent sequence; the difference is
    which model tier each agent runs on.
    """
    return [
        "or-interviewer",
        "or-classifier",
        "or-solver-fit",
        # User confirmation break
        "or-extractor",
        "or-formulator",
        "or-coder",
        "or-verifier",
        "or-reporter",
    ]
