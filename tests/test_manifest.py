import json
from pathlib import Path

from vllm_hust_ext.manifest import activation_blocker, load_manifest

import stateaxis_incremental_eviction


def test_descriptor_is_discoverable_but_not_activatable() -> None:
    manifest = load_manifest(
        Path(stateaxis_incremental_eviction.__file__).with_name(
            "vllm-hust-extension-v0.3.json"
        )
    )
    assert manifest.bundle_id == "org.vllm-hust.stateaxis-incremental-eviction"
    assert manifest.schema_version == "0.3-experimental"
    assert activation_blocker(manifest) is not None


def test_native_candidate_is_extracted_but_not_claimed_as_active() -> None:
    repository = Path(stateaxis_incremental_eviction.__file__).parents[2]
    provenance = json.loads((repository / "PROVENANCE.json").read_text())
    boundary = provenance["implementation_boundary"]
    assert provenance["implementation_extracted"] is True
    assert boundary["path"] == "native"
    assert boundary["activation_status"] == "not_wired"
    assert boundary["performance_qualified"] is False
    assert (repository / "native" / "src" / "lib.rs").is_file()
