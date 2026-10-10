# Bitmap eviction component crossover — Kunpeng 920

Evidence label: `component-crossover-superseded-precomputed-utility`; online
performance qualification: `false`. This evidence is retained unchanged as a
historical result, but its activation boundary is superseded by
`../bitmap-dynamic-age-crossover-kunpeng920-20261010/`, which includes dynamic
age-score computation in both arms.

This is a three-process Rust component benchmark on a Kunpeng 920 aarch64 host.
Each process measured 20,000 iterations per cell. The reference allocates and
full-sorts eligible records using the exact eviction ordering; the candidate
incrementally maintains stable slots plus a 64-bit eligibility bitmap. Both
arms clone the selected handles, so the return-value cost is matched.

| Records | Victims | Reference P50 | Bitmap P50 | Change | Decision |
| ---: | ---: | ---: | ---: | ---: | --- |
| 17 | 1 | 430 ns | 150 ns | -65.12% | bitmap |
| 17 | 4 | 510 ns | 370 ns | -27.45% | bitmap |
| 17 | 8 | 630 ns | 730 ns | +15.87% | full-sort fallback |
| 32 | 1 | 890 ns | 200 ns | -77.53% | bitmap |
| 32 | 4 | 980 ns | 660 ns | -32.65% | bitmap |
| 64 | 1 | 2,050 ns | 350 ns | -82.93% | bitmap |
| 64 | 4 | 2,100 ns | 1,220 ns | -41.90% | bitmap |

This original candidate was bounded to at most four victims per selection. That
boundary must no longer be used: once dynamic age-score computation is included,
only the single-victim cells remain positive. The negative 17/8 result is retained
in `raw.csv`.

Five unit tests cover exact full-sort equivalence across 64 generated records,
generation safety, pinned/pending eligibility updates, slot reuse, capacity
failure, and bulk fallback. `cargo clippy --all-targets -- -D warnings` passes.

This evidence isolates CPU selector cost. It does not establish NPU, HTTP,
Qwen, AgentX, or end-to-end benefit. Host wiring, lifecycle/failure recovery,
matched ON/OFF services, peak HBM, and exact output gates remain required.
