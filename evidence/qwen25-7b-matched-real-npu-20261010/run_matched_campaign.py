#!/usr/bin/env python3
"""Matched real-NPU ON/OFF campaign for StateAxis incremental eviction."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import statistics
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLI = "/root/mod-modernization/manager-main/.venv/bin/vllm-hust-ext"
ENGINE = "/root/stateaxis/target/release/state-engine"
BACKEND = (
    "/root/frontier-kvmat-env/bin/python /root/stateaxis/backend/worker.py "
    "--model /models/Qwen2.5-7B-Instruct --device npu:0 --dtype bf16 "
    "--attention-backend eager"
)
CONFIG = {
    "ON": str(ROOT / "manager-state/config.json"),
    "OFF": str(ROOT / "manager-off-state/config.json"),
}
ORDER = (("OFF", "ON"), ("ON", "OFF"), ("OFF", "ON"))
REQUESTS = 64
MAX_TOKENS = 4
MAX_STATES = 17


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(repo: str, *args: str) -> str:
    return subprocess.check_output(["git", "-C", repo, *args], text=True).strip()


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def distribution(values: list[float]) -> dict[str, float]:
    return {
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "mean": statistics.fmean(values),
    }


def hbm_mb() -> int:
    output = subprocess.check_output(["npu-smi", "info"], text=True)
    usages = [int(value) for value in re.findall(r"(\d+)\s*/\s*65536", output)]
    if not usages:
        raise RuntimeError("unable to parse NPU 6 HBM usage")
    return usages[0]


def npu_processes() -> list[str]:
    output = subprocess.check_output(["npu-smi", "info"], text=True)
    if "No running processes found in NPU 6" in output:
        return []
    return [
        line
        for line in output.splitlines()
        if "state-engine" in line or "python" in line
    ]


def request_json(url: str, payload: dict | None = None, timeout: int = 180) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def wait_ready(
    base_url: str, process: subprocess.Popen, timeout: float = 180.0
) -> float:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout:
        if process.poll() is not None:
            raise RuntimeError(
                f"service exited during startup with {process.returncode}"
            )
        try:
            if request_json(base_url + "/health", timeout=2).get("status") == "ok":
                return time.perf_counter() - started
        except Exception:
            time.sleep(0.25)
    raise TimeoutError("StateAxis service did not become ready")


def stop_service(process: subprocess.Popen) -> tuple[int, bool]:
    process.send_signal(signal.SIGINT)
    forced = False
    try:
        return process.wait(timeout=45), forced
    except subprocess.TimeoutExpired:
        forced = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            return process.wait(timeout=15), forced
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            return process.wait(timeout=10), True


def run_arm(pair: int, position: int, arm: str, port: int) -> dict:
    run_id = f"pair-{pair + 1}-{position + 1}-{arm.lower()}"
    log_path = ROOT / f"{run_id}.log"
    result_path = ROOT / f"{run_id}.json"
    environment = os.environ.copy()
    environment.update(
        {
            "VLLM_HUST_EXT_CONFIG": CONFIG[arm],
            "ASCEND_RT_VISIBLE_DEVICES": "0",
            "PYTHONPATH": "/root/stateaxis",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "RUST_LOG": "info",
        }
    )
    command = [
        CLI,
        "run",
        "--shutdown-grace-seconds",
        "30",
        "--",
        ENGINE,
        "--listen",
        f"127.0.0.1:{port}",
        "--backend-command",
        BACKEND,
        "--model-revision",
        "qwen2.5-7b-instruct-local",
        "--max-states",
        str(MAX_STATES),
        "--max-state-bytes",
        "60000000000",
        "--scheduling-policy",
        "fifo_continuous",
        "--max-batch-size",
        "1",
    ]
    baseline_hbm = hbm_mb()
    if npu_processes():
        raise RuntimeError("NPU 6 is not idle before run")
    samples: list[dict[str, float | int]] = []
    stop_sampling = threading.Event()

    def sample() -> None:
        origin = time.perf_counter()
        while not stop_sampling.is_set():
            with contextlib.suppress(Exception):
                samples.append(
                    {"seconds": time.perf_counter() - origin, "hbm_mb": hbm_mb()}
                )
            stop_sampling.wait(0.20)

    sampler = threading.Thread(target=sample, daemon=True)
    responses: list[dict] = []
    errors: list[dict] = []
    process = None
    forced_stop = False
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd="/root/stateaxis",
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        sampler.start()
        try:
            base_url = f"http://127.0.0.1:{port}"
            startup_seconds = wait_ready(base_url, process)
            for warmup in range(3):
                request_json(
                    base_url + "/v1/generate",
                    {
                        "prompt": f"Warmup {warmup}: state eviction invariant.",
                        "max_tokens": MAX_TOKENS,
                        "state_scope": f"warmup-{warmup}",
                        "quality_epoch": "matched-v1",
                        "retain_prompt_state": False,
                    },
                )
            workload_started = time.perf_counter()
            for index in range(REQUESTS):
                payload = {
                    "prompt": (
                        f"State eviction benchmark request {index}: "
                        "return a short invariant."
                    ),
                    "max_tokens": MAX_TOKENS,
                    "state_scope": f"matched-{index}",
                    "quality_epoch": "matched-v1",
                    "retain_prompt_state": True,
                }
                started = time.perf_counter()
                try:
                    response = request_json(base_url + "/v1/generate", payload)
                    response["client_e2e_ms"] = (time.perf_counter() - started) * 1000.0
                    response["request_index"] = index
                    responses.append(response)
                except Exception as error:
                    errors.append({"request_index": index, "error": repr(error)})
            workload_seconds = time.perf_counter() - workload_started
            metrics = request_json(base_url + "/metrics", timeout=10)
        finally:
            if process.poll() is None:
                return_code, forced_stop = stop_service(process)
            else:
                return_code = process.returncode
            stop_sampling.set()
            sampler.join(timeout=5)
    release_deadline = time.time() + 30
    while time.time() < release_deadline and npu_processes():
        time.sleep(0.5)
    release_hbm = hbm_mb()
    released = not npu_processes() and release_hbm <= baseline_hbm + 64
    ttft = [float(item["ttft_ms"]) for item in responses]
    tpot = [
        float(item["tpot_ms"]) for item in responses if item.get("tpot_ms") is not None
    ]
    e2e = [float(item["client_e2e_ms"]) for item in responses]
    output_tokens = sum(int(item["generated_tokens"]) for item in responses)
    result = {
        "schema_version": "stateaxis.incremental-eviction.matched-real-npu/v1",
        "evidence_label": "matched_real_online_experimental_unqualified",
        "run_id": run_id,
        "pair": pair + 1,
        "position": position + 1,
        "arm": arm,
        "command": command,
        "manager_config": CONFIG[arm],
        "baseline_hbm_mb": baseline_hbm,
        "peak_hbm_mb": max(
            (int(item["hbm_mb"]) for item in samples), default=baseline_hbm
        ),
        "release_hbm_mb": release_hbm,
        "resources_released": released,
        "forced_stop": forced_stop,
        "service_return_code": return_code,
        "startup_seconds": startup_seconds,
        "workload_seconds": workload_seconds,
        "request_count": REQUESTS,
        "success_count": len(responses),
        "errors": errors,
        "error_rate": len(errors) / REQUESTS,
        "request_throughput_rps": len(responses) / workload_seconds,
        "output_token_throughput_tps": output_tokens / workload_seconds,
        "output_tokens": output_tokens,
        "ttft_ms": distribution(ttft),
        "tpot_ms": distribution(tpot),
        "e2e_ms": distribution(e2e),
        "output_token_ids": [item["output_token_ids"] for item in responses],
        "engine_metrics": metrics,
        "hbm_samples": samples,
        "log": log_path.name,
    }
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def delta(on: float, off: float) -> float:
    return (on / off - 1.0) * 100.0


def main() -> None:
    identity = {
        "stateaxis_commit": git("/root/stateaxis", "rev-parse", "HEAD"),
        "stateaxis_dirty": bool(git("/root/stateaxis", "status", "--porcelain")),
        "manager_commit": git("/root/extension-manager", "rev-parse", "HEAD"),
        "manager_dirty": bool(git("/root/extension-manager", "status", "--porcelain")),
        "mod_commit": git(
            "/root/stateaxis-topic-mods/repositories/stateaxis-incremental-eviction",
            "rev-parse",
            "HEAD",
        ),
        "mod_dirty": bool(
            git(
                "/root/stateaxis-topic-mods/repositories/stateaxis-incremental-eviction",
                "status",
                "--porcelain",
            )
        ),
        "research_manifest_sha256": sha256(
            "/root/stateaxis-topic-mods/repositories/stateaxis-incremental-eviction/RESEARCH_MANIFEST.json"
        ),
        "model_config_sha256": sha256("/models/Qwen2.5-7B-Instruct/config.json"),
        "model_path": "/models/Qwen2.5-7B-Instruct",
        "hardware": "1x visible logical Ascend 910B2 (physical NPU 6)",
        "graph_mode": "eager",
        "dtype": "bf16",
        "backend": "transformers + torch_npu",
    }
    (ROOT / "identity.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n"
    )
    runs = []
    port = 18100
    for pair_index, pair_order in enumerate(ORDER):
        for position, arm in enumerate(pair_order):
            result_path = (
                ROOT / f"pair-{pair_index + 1}-{position + 1}-{arm.lower()}.json"
            )
            if result_path.exists():
                runs.append(json.loads(result_path.read_text()))
            else:
                runs.append(run_arm(pair_index, position, arm, port))
            port += 1
    oracle = runs[0]["output_token_ids"]
    exact = all(run["output_token_ids"] == oracle for run in runs)
    pairs = []
    for pair_index in range(3):
        pair_runs = [run for run in runs if run["pair"] == pair_index + 1]
        on = next(run for run in pair_runs if run["arm"] == "ON")
        off = next(run for run in pair_runs if run["arm"] == "OFF")
        pairs.append(
            {
                "pair": pair_index + 1,
                "request_throughput_delta_percent": delta(
                    on["request_throughput_rps"], off["request_throughput_rps"]
                ),
                "output_token_throughput_delta_percent": delta(
                    on["output_token_throughput_tps"],
                    off["output_token_throughput_tps"],
                ),
                "ttft_p50_delta_percent": delta(
                    on["ttft_ms"]["p50"], off["ttft_ms"]["p50"]
                ),
                "tpot_p50_delta_percent": delta(
                    on["tpot_ms"]["p50"], off["tpot_ms"]["p50"]
                ),
                "e2e_p50_delta_percent": delta(
                    on["e2e_ms"]["p50"], off["e2e_ms"]["p50"]
                ),
                "peak_hbm_delta_mb": on["peak_hbm_mb"] - off["peak_hbm_mb"],
            }
        )
    on_runs = [run for run in runs if run["arm"] == "ON"]
    off_runs = [run for run in runs if run["arm"] == "OFF"]
    effect_exercised = all(
        run["engine_metrics"].get("bitmap_eviction_authority_applied", 0) > 0
        and run["engine_metrics"].get("bitmap_eviction_full_sort_fallbacks", 1) == 0
        for run in on_runs
    ) and all(
        not run["engine_metrics"].get("bitmap_eviction_active", False)
        for run in off_runs
    )
    summary = {
        "schema_version": "stateaxis.incremental-eviction.matched-real-npu-summary/v1",
        "evidence_label": "matched_real_online_experimental_unqualified",
        "identity": identity,
        "pair_order": ORDER,
        "runs": [run["run_id"] for run in runs],
        "output_exact_across_all_runs": exact,
        "effect_exercised": effect_exercised,
        "all_resources_released": all(run["resources_released"] for run in runs),
        "all_error_rates_zero": all(run["error_rate"] == 0 for run in runs),
        "paired_deltas": pairs,
        "median_paired_deltas": {
            key: statistics.median(pair[key] for pair in pairs)
            for key in pairs[0]
            if key != "pair"
        },
        "performance_qualified": False,
        "qualification_note": (
            "Experimental matched evidence; promotion requires repeated positive "
            "end-to-end deltas without correctness or lifecycle regressions."
        ),
    }
    (ROOT / "SUMMARY.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
