# stateaxis-incremental-eviction

Extension ID: `org.vllm-hust.stateaxis-incremental-eviction`

Incremental candidate index replacing full-sort state eviction.

This repository is the independent MOD boundary for StateAxis issue #10.
It is deliberately `import_only`, default-off, and cannot be enabled. The split does
not inherit correctness, device, performance, or publication qualification from the
aggregate StateAxis repository.

## Evidence boundary

Status: **component-positive candidate; online untested and not qualified**.

The preserved lazy-heap candidate was exact but about 3.37x slower than full sort
at the measured 17-state serving capacity. A newly authored bounded bitmap index
removes the heap/map clone from selection. Across three component processes it
reduced the 17-state single-victim P50 from 430 ns to 150 ns (-65.12%). The
17-state/eight-victim cell regressed 15.87%, so selections above four victims
explicitly fall back to full sort. See
`evidence/bitmap-crossover-kunpeng920-20261010/`.

The copied evidence and its SHA-256 are recorded in `PROVENANCE.json`. Negative,
failed, and inconclusive results are retained. Microbenchmarks and component results
must not be restated as online end-to-end gains.

## Install and inspect

```bash
python -m pip install .
vllm-hust-ext extension inspect org.vllm-hust.stateaxis-incremental-eviction
vllm-hust-ext extension check org.vllm-hust.stateaxis-incremental-eviction
```

Discovery does not enable the MOD. A future active revision must extract an
independently reviewable implementation, declare exclusive resources where needed,
and pass exactness, lifecycle, release, failure-recovery, and matched real-online
gates.

The independently reviewable implementation now lives under `native/`, but the
Manifest intentionally remains `import_only` until the StateAxis host consumes the
fail-closed bitmap/full-sort crossover contract. Component timing must not be
restated as online or NPU benefit.

## Validate

```bash
python -m pip install -e '.[test]'
pytest -q
```

Maintainer: Shuhao Zhang (Tony), directly responsible; no advisor is declared.
