# Qwen2.5-7B matched real-NPU ON/OFF result

Evidence label: `matched_real_online_experimental_unqualified`.

This campaign tested the active `org.vllm-hust.stateaxis-incremental-eviction`
MOD through vLLM-HUST Extension Manager/ECPA. It is not a simulation, replay,
or projected profile.

## Frozen identity

- StateAxis: `85e2b9095c01ad13f290553b789aa8f4a0ae10d5`, clean
- Extension Manager: `00d1b940dc6ce8d60e2cd28708b80d80e9c33a09`, clean
- tested MOD: `17e51a604988165523628c9e8d126949054c64e6`, clean
- tested research-manifest SHA-256:
  `abae21ac5270c9cbe92df592ccc3657b83e935a6efdb8d6c18d81c36950452d7`
- Rust mechanism dependency: `bc067493685d2d872a03ce408e3e0a0b741756c6`
- model: `/models/Qwen2.5-7B-Instruct`; `config.json` SHA-256
  `7463bb0ea78315365e6c6b74de4e73bbcc8359dfb0c5a737584e077d42c0b03c`
- device: one logical Ascend 910B2 (physical NPU 6), eager BF16
- backend: Transformers + `torch_npu`; no graph mode

The evidence release is version 0.2.1 because it changes the research record;
the measured mechanism and activation identity were version 0.2.0 above.

## Protocol

- Pair order: `OFF/ON`, `ON/OFF`, `OFF/ON`.
- Every arm used a fresh service and model load.
- Three unretained warmups preceded 64 sequential retained-state requests.
- Capacity was 17 states; each request generated up to four greedy tokens.
- OFF and ON used the same command, model, prompt order, and device. The only
  difference was the Manager-owned enablement state.
- HBM was sampled from `npu-smi`; client E2E and engine TTFT/TPOT were retained.

| Run | req/s | TTFT p50 ms | TPOT p50 ms | E2E p50 ms | peak HBM MB | authority | fallback |
|---|---:|---:|---:|---:|---:|---:|---:|
| pair-1 OFF | 3.9151 | 70.437 | 61.129 | 255.225 | 18252 | 0 | 0 |
| pair-1 ON | 3.8652 | 71.220 | 61.956 | 258.566 | 18253 | 47 | 0 |
| pair-2 ON | 3.8118 | 71.871 | 62.941 | 262.108 | 18252 | 47 | 0 |
| pair-2 OFF | 3.8116 | 72.074 | 63.165 | 262.793 | 18253 | 0 | 0 |
| pair-3 OFF | 3.8023 | 72.646 | 63.596 | 264.527 | 18254 | 0 | 0 |
| pair-3 ON | 3.9261 | 69.920 | 60.937 | 254.650 | 18252 | 47 | 0 |

Paired request/output-token throughput deltas were **-1.276%, +0.005%, and
+3.257%**; median **+0.005%**. Median paired p50 deltas were TTFT -0.282%, TPOT
-0.354%, and E2E -0.261%. The signs did not repeat, so the result is neutral or
mixed at this workload scale and no performance promotion is permitted.

## Correctness, effect, lifecycle, and failure gates

- All six runs produced identical output-token IDs for every request.
- All error rates were zero.
- Every ON run recorded 47 authoritative bitmap evictions, zero full-sort
  fallback, and zero capacity disable; every OFF run reported the mechanism
  inactive.
- Every service stopped without forced termination, no NPU process remained,
  and HBM returned to baseline.
- A deliberately mismatched research-manifest digest was rejected by the
  Manager before launch (`failure-manager-digest.log`, exit 2).
- An unknown host config field was rejected before the backend command ran
  (`failure-host-config.log`, exit 1; forbidden marker was not created).

`SUMMARY.json` is the compact result. `pair-*.json` contains raw per-request
tokens, latency distributions, HBM samples, and effect metrics. The harness and
configuration files are included for reproduction.
