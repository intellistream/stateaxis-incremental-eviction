import hashlib
import json
from pathlib import Path

from vllm_hust_ext.cli import _merge_provider_plan
from vllm_hust_ext.manifest import activation_blocker, load_manifest
from vllm_hust_ext.providers.stateaxis import StateAxisProvider

import stateaxis_incremental_eviction


def manifest_path() -> Path:
    return Path(stateaxis_incremental_eviction.__file__).with_name(
        "vllm-hust-extension-v0.3.json"
    )


def research_manifest_path() -> Path:
    return Path(stateaxis_incremental_eviction.__file__).parents[2] / (
        "RESEARCH_MANIFEST.json"
    )


def test_policy_is_discoverable_and_experimentally_activatable() -> None:
    manifest = load_manifest(manifest_path())
    assert manifest.bundle_id == "org.vllm-hust.stateaxis-incremental-eviction"
    assert manifest.bundle_version == "0.2.0"
    assert manifest.schema_version == "0.3-experimental"
    assert activation_blocker(manifest) is None
    additional = dict(manifest.activation.additional_config)
    assert (
        additional["stateaxis_mod"]["manifest_sha256"]
        == hashlib.sha256(research_manifest_path().read_bytes()).hexdigest()
    )
    assert additional["stateaxis_mod"]["performance_qualified"] is False
    assert additional["stateaxis_incremental_eviction"] == {
        "bitmap_enabled": True,
        "single_victim_only": True,
        "max_index_states": 64,
        "fail_closed": True,
    }


def test_native_candidate_is_extracted_and_bound_to_the_active_host() -> None:
    repository = Path(stateaxis_incremental_eviction.__file__).parents[2]
    provenance = json.loads((repository / "PROVENANCE.json").read_text())
    boundary = provenance["implementation_boundary"]
    assert provenance["implementation_extracted"] is True
    assert boundary["path"] == "native"
    assert boundary["activation_status"] == "active_experimental"
    assert boundary["host_commit"] == "742d4860322dd0e9e55163752d7bda311b6f55c7"
    assert (
        boundary["research_manifest_sha256"]
        == hashlib.sha256(research_manifest_path().read_bytes()).hexdigest()
    )
    assert boundary["performance_qualified"] is False
    assert (repository / "native" / "src" / "lib.rs").is_file()


def test_research_manifest_matches_package_contract() -> None:
    payload = json.loads(research_manifest_path().read_text())
    assert payload["mod_id"] == stateaxis_incremental_eviction.MOD_ID
    assert payload["version"] == "0.2.0"
    assert payload["mechanism"] == {
        "name": "generation-safe-bounded-bitmap-eviction",
        "bitmap_enabled": True,
        "single_victim_only": True,
        "max_index_states": 64,
        "fail_closed": True,
    }
    assert payload["qualification"]["performance_qualified"] is False


def test_manager_forwards_the_hash_bound_mechanism_config() -> None:
    manifest = load_manifest(manifest_path())
    configuration = {
        "experiment_mode": True,
        "host_version": "1.0.0",
        "protocol_versions": {"stateaxis.mod-proposal.incremental-eviction": "1.0"},
        "research_manifest_path": str(research_manifest_path()),
    }
    check = StateAxisProvider().check(manifest, configuration)
    assert check.compatible is True
    assert check.configured is True
    assert check.degraded is True
    plan = StateAxisProvider().plan(manifest, configuration, enabled=True)
    assert plan.actions[0].operation == "configure_experiment_launch"
    command = _merge_provider_plan(["stateaxis"], plan)
    assert command[1] == "--additional-config"
    additional = json.loads(command[2])
    assert additional["experiment_mode"] is True
    assert additional["stateaxis_incremental_eviction"] == {
        "bitmap_enabled": True,
        "single_victim_only": True,
        "max_index_states": 64,
        "fail_closed": True,
    }
    assert (
        additional["stateaxis_mod"]["manifest_sha256"]
        == hashlib.sha256(research_manifest_path().read_bytes()).hexdigest()
    )


def test_handler_refuses_out_of_contract_variants() -> None:
    assert stateaxis_incremental_eviction.incremental_eviction().max_index_states == 64
    try:
        stateaxis_incremental_eviction.IncrementalEvictionConfig(max_index_states=65)
    except ValueError as error:
        assert "bounded 64-state" in str(error)
    else:
        raise AssertionError("out-of-contract capacity must fail closed")
