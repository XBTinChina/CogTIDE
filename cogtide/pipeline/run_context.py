"""Run context: holds all run-level state and services.

A RunContext is created once at pipeline start and threaded through
every stage. It owns the run directory, the LLM client, the
checkpoint manager, the artifact registry, and the agent registry.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cogtide.llm.client import LLMClient, ModelConfig, RetryConfig
from cogtide.pipeline.artifact_registry import ArtifactRegistry
from cogtide.pipeline.checkpoint_manager import CheckpointManager
from cogtide.registry import AgentRegistry
from cogtide.utils.ids import make_run_id, slugify
from cogtide.utils.io import read_json, write_json

RUNS_ROOT = Path(__file__).resolve().parents[2] / "runs"
CONFIGS_ROOT = Path(__file__).resolve().parents[2] / "configs"


def _load_env_file() -> None:
    """Best-effort .env loader: utf-8-sig, placeholder-safe, non-overriding.

    - Reads with utf-8-sig to tolerate Windows BOMs.
    - ``os.environ.setdefault`` so shell exports win over file entries.
    - Skips obvious placeholder values (sk-replace-me, your-key, etc.).
    """
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        # Fallback: Windows users sometimes save as .env.txt.
        alt = env_path.with_suffix(".env.txt")
        if alt.exists():
            print(f"[env] found {alt.name}; expected .env — please rename")
        return
    placeholders = {
        "sk-replace-me",
        "sk-your-real-key-here",
        "your-key-here",
        "0000000000000000000000000000000000000000",
        "",
    }
    try:
        raw = env_path.read_text(encoding="utf-8-sig")
    except Exception as e:
        print(f"[env] failed to read {env_path}: {e}")
        return
    loaded = 0
    for line in raw.splitlines():
        line = line.lstrip("\ufeff").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or value in placeholders or value.startswith("sk-replace"):
            continue
        if os.environ.get(key):
            continue
        os.environ.setdefault(key, value)
        loaded += 1
    if loaded:
        print(f"[env] loaded {loaded} key(s) from {env_path.name}")


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge overlay into base. Overlay wins on leaf collisions."""
    out = dict(base)
    for k, v in overlay.items():
        if (
            k in out
            and isinstance(out[k], dict)
            and isinstance(v, dict)
        ):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class RunContext:
    """Immutable-ish bag of run-level state."""

    run_id: str
    run_dir: Path
    client: LLMClient
    checkpoint: CheckpointManager
    artifacts: ArtifactRegistry
    agents: AgentRegistry
    config: dict[str, Any] = field(default_factory=dict)

    def stage_dir(self, stage: str) -> Path:
        """Return (and create) the directory for a stage's artifacts."""
        d = self.run_dir / stage
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def create(
        cls,
        topic: str,
        *,
        run_id: str | None = None,
        config_overrides: dict[str, Any] | None = None,
    ) -> "RunContext":
        """Bootstrap a new run from a topic string.

        1. Loads .env if present (for API keys).
        2. Reads configs/models.yaml, configs/retries.yaml, configs/pipeline.yaml.
        3. Applies any learned-policy overlay.
        4. Creates the run directory tree.
        5. Instantiates services.
        """
        _load_env_file()

        # Load configs
        model_cfg_path = CONFIGS_ROOT / "models.yaml"
        retry_cfg_path = CONFIGS_ROOT / "retries.yaml"
        pipeline_cfg_path = CONFIGS_ROOT / "pipeline.yaml"

        model_data = yaml.safe_load(model_cfg_path.read_text(encoding="utf-8-sig")) or {}
        default_model = model_data.get("default", {})
        retry_data = yaml.safe_load(retry_cfg_path.read_text(encoding="utf-8-sig")) or {}
        pipeline_data: dict[str, Any] = {}
        if pipeline_cfg_path.exists():
            pipeline_data = yaml.safe_load(
                pipeline_cfg_path.read_text(encoding="utf-8-sig")
            ) or {}

        model_config = ModelConfig(
            provider=default_model.get("provider", "openai-compatible"),
            api_base_url=default_model.get("api_base_url", "https://api.openai.com/v1"),
            api_key_env=default_model.get("api_key_env", "LLM_API_KEY"),
            fallback_api_key_env=default_model.get("fallback_api_key_env", "OPENAI_API_KEY"),
            model=default_model.get("model", "gpt-4o-mini"),
            temperature=float(default_model.get("temperature", 1.0)),
            max_tokens=int(default_model.get("max_tokens", 8192)),
            response_format_json=bool(default_model.get("response_format_json", True)),
        )

        waits = retry_data.get("waits_seconds", [5, 15, 30, 60, 120])
        retry_config = RetryConfig(
            attempts=int(retry_data.get("attempts", 5)),
            waits_seconds=tuple(waits),
            timeout_seconds=int(retry_data.get("timeout_seconds", 300)),
            concurrency_limit=int(retry_data.get("concurrency_limit", 2)),
            min_request_interval_seconds=float(
                retry_data.get("min_request_interval_seconds", 1.0)
            ),
            rate_limit_backoff_multiplier=float(
                retry_data.get("rate_limit_backoff_multiplier", 4.0)
            ),
            retry_jitter=float(retry_data.get("retry_jitter", 0.5)),
        )

        # Apply learned policy overlay. Merge pipeline.yaml first so stages
        # and memory knobs flow into ctx.config.
        from cogtide.memory.policy import apply_policy_overlay
        merged = _deep_merge(model_data, pipeline_data)
        config = apply_policy_overlay(merged)
        if config_overrides:
            config = _deep_merge(config, config_overrides)

        # Create run
        rid = run_id or make_run_id(slugify(topic))
        run_dir = RUNS_ROOT / rid
        run_dir.mkdir(parents=True, exist_ok=True)

        # Save run metadata
        write_json(run_dir / "run_meta.json", {
            "run_id": rid,
            "topic": topic,
            "model": model_config.model,
            "config": config,
        })

        client = LLMClient(model_config=model_config, retry_config=retry_config)
        checkpoint = CheckpointManager(run_dir)
        artifact_registry = ArtifactRegistry(run_dir)
        agent_registry = AgentRegistry.load()

        return cls(
            run_id=rid,
            run_dir=run_dir,
            client=client,
            checkpoint=checkpoint,
            artifacts=artifact_registry,
            agents=agent_registry,
            config=config,
        )

    @classmethod
    def resume(cls, run_id: str) -> "RunContext":
        """Resume an existing run by its run_id."""
        run_dir = RUNS_ROOT / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"No run directory for {run_id}")

        meta = read_json(run_dir / "run_meta.json")
        topic = meta.get("topic", "")

        return cls.create(topic, run_id=run_id)
