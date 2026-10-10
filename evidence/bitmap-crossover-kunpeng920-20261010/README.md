# Bitmap eviction component crossover — Kunpeng 920

Evidence label: `component-repeated-crossover-positive`; online performance
qualification: `false`.

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

The active candidate is deliberately bounded to at most four victims per
selection. Larger bulk selections return `None` from `preview_bounded`, so the
host must preserve its full-sort authority. The negative 17/8 result is retained
in `raw.csv`; it is the reason for this fail-closed crossover boundary.

Five unit tests cover exact full-sort equivalence across 64 generated records,
generation safety, pinned/pending eligibility updates, slot reuse, capacity
failure, and bulk fallback. `cargo clippy --all-targets -- -D warnings` passes.

This evidence isolates CPU selector cost. It does not establish NPU, HTTP,
Qwen, AgentX, or end-to-end benefit. Host wiring, lifecycle/failure recovery,
matched ON/OFF services, peak HBM, and exact output gates remain required.
