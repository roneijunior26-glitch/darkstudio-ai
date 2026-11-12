"""Reconstrucao incremental: so refaz o que depende do que mudou.

`input_hash` identifica as entradas de um artefato. `artifacts_to_rebuild`
diz quais artefatos de uma cena precisam ser regenerados quando campos mudam
(criterio de aceitacao 14: substituir uma cena sem reconstruir o projeto).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

HASH_VERSION = "v1"

# Campos da cena que alimentam cada artefato.
ARTIFACT_INPUTS: dict[str, tuple[str, ...]] = {
    "image": ("image_prompt", "visual_style", "seed", "character_refs"),
    "audio": ("narration_text", "voice_id", "speed"),
    "subtitles": ("narration_text", "subtitle_style"),
    "clip": ("camera_move", "transition", "anim_intensity", "video_prompt", "media_type"),
}

# Artefatos que dependem de outros artefatos.
ARTIFACT_DEPENDS_ON: dict[str, tuple[str, ...]] = {
    "subtitles": ("audio",),
    "clip": ("image", "audio", "subtitles"),
}


def input_hash(inputs: dict[str, Any], *, salt: str = HASH_VERSION) -> str:
    canonical = json.dumps(
        inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(f"{salt}:{canonical}".encode("utf-8")).hexdigest()


def needs_rebuild(stored_hash: str | None, inputs: dict[str, Any]) -> bool:
    return stored_hash is None or stored_hash != input_hash(inputs)


def artifacts_to_rebuild(old: dict[str, Any], new: dict[str, Any]) -> set[str]:
    changed = {
        artifact
        for artifact, fields in ARTIFACT_INPUTS.items()
        if any(old.get(f) != new.get(f) for f in fields)
    }
    # Propaga para quem depende dos artefatos alterados, ate estabilizar.
    grew = True
    while grew:
        grew = False
        for artifact, deps in ARTIFACT_DEPENDS_ON.items():
            if artifact not in changed and any(d in changed for d in deps):
                changed.add(artifact)
                grew = True
    return changed
