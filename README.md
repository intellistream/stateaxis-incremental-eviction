# stateaxis-incremental-eviction

Extension ID: `org.vllm-hust.stateaxis-incremental-eviction`

Incremental candidate index replacing full-sort state eviction.

This repository is the independent MOD boundary for StateAxis issue #10.
It is default-off and can be enabled only through the vLLM-HUST Extension Manager
StateAxis provider in explicit experiment mode. The split does not inherit correctness,
device, performance, or publication qualification from the aggregate StateAxis repository.

## Evidence boundary

Status: **component-positive candidate; online untested and not qualified**.

The preserved lazy-heap candidate was exact but about 3.37x slower than full sort
at the measured 17-state serving capacity. A newly authored bounded bitmap index
removes the heap/map clone from selection. The first crossover precomputed
utility and is retained as superseded evidence. A stricter three-process rerun
computed the dynamic age-adjusted score in both arms: single-victim P50 improved
by 50.00% at 17 states, 59.66% at 32 states, and 66.17% at 64 states. Every
four/eight-victim cell regressed, so only exactly one victim may use the bitmap;
bulk selection must fail closed to full sort. See
`evidence/bitmap-dynamic-age-crossover-kunpeng920-20261010/`.

The copied evidence and its SHA-256 are recorded in `PROVENANCE.json`. Negative,
failed, and inconclusive results are retained. Microbenchmarks and component results
must not be restated as online end-to-end gains.

## Install and inspect

```bash
python -m pip install .
vllm-hust-ext extension inspect org.vllm-hust.stateaxis-incremental-eviction
vllm-hust-ext extension check org.vllm-hust.stateaxis-incremental-eviction
```

Discovery alone does not enable the MOD. The active Manifest 0.3 contract is accepted
only with `experiment_mode=true`, a verified `RESEARCH_MANIFEST.json` digest, and the
matching host identity. The independently reviewable implementation lives under
`native/`; StateAxis host commit `742d4860322dd0e9e55163752d7bda311b6f55c7`
wires it into the real eviction lifecycle and exports decisions, authority applications,
full-sort fallbacks, and capacity disables. Component timing must not be restated as
online or NPU benefit.

## Validate

```bash
python -m pip install -e '.[test]'
pytest -q
```

Maintainer: Shuhao Zhang (Tony), directly responsible; no advisor is declared.
