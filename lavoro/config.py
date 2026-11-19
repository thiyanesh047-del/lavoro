from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _from_example(name: str, example: str) -> Path:
    """First run: create your own copy from the example file (your copy is never committed)."""
    p = ROOT / name
    if not p.exists() and (ROOT / example).exists():
        p.write_text((ROOT / example).read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Created {name} from {example}. Edit it to make Lavoro yours.")
    return p


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else _from_example("config.yaml", "config.example.yaml")
    _from_example("profile.md", "profile.example.md")
    with open(p, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg["_root"] = str(ROOT)
    return cfg


def read_profile(cfg: dict) -> str:
    name = cfg.get("me", {}).get("profile_file", "profile.md")
    p = _from_example(name, "profile.example.md") if name == "profile.md" else ROOT / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def output_dir(cfg: dict) -> Path:
    d = ROOT / cfg.get("output_dir", "output")
    d.mkdir(parents=True, exist_ok=True)
    return d


def has_claude() -> bool:
    from . import llm
    return llm.backend() is not None


def min_score(cfg: dict) -> float:
    lc = cfg.get("llm", {})
    return lc.get("min_score", 7) if has_claude() else lc.get("min_score_without_claude", 4)
