# Dynamic-age bitmap eviction crossover — Kunpeng 920

Evidence label: `component-repeated-crossover-positive-single-victim`; online
performance qualification: `false`.

This follow-up includes the production eviction score in both arms:
`value_density / sqrt(max(age_seconds, 1))`. It supersedes the earlier
precomputed-utility crossover for activation decisions while preserving that raw
evidence. Three independent processes measured 20,000 iterations per cell. Both
arms clone selected handles.

| Records | Victims | Reference P50 | Bitmap P50 | Change | Decision |
| ---: | ---: | ---: | ---: | ---: | --- |
| 17 | 1 | 600 ns | 300 ns | -50.00% | bitmap |
| 32 | 1 | 1,190 ns | 480 ns | -59.66% | bitmap |
| 64 | 1 | 2,660 ns | 900 ns | -66.17% | bitmap |
| 17 | 4 | 670 ns | 930 ns | +38.81% | full-sort fallback |
| 17 | 8 | 860 ns | 3,060 ns | +255.81% | full-sort fallback |
| 32 | 4 | 1,280 ns | 1,710 ns | +33.59% | full-sort fallback |
| 32 | 8 | 1,470 ns | 5,600 ns | +280.95% | full-sort fallback |
| 64 | 4 | 2,740 ns | 3,380 ns | +23.36% | full-sort fallback |
| 64 | 8 | 2,940 ns | 9,010 ns | +206.46% | full-sort fallback |

The candidate therefore exposes a fail-closed bounded API only for exactly one
victim and at most 64 live states. Zero victims is a harmless empty selection.
Two or more victims, capacity overflow, identity mismatch, or host-side index
drift must retain the existing full-sort authority.

Six unit tests cover exact dynamic-score ordering, generation safety,
pinned/pending eligibility changes, metadata refresh, slot reuse, capacity
failure, and the single-victim boundary. Rust formatting, tests, and clippy with
warnings denied pass.

This is a CPU component crossover, not an NPU or end-to-end result. StateAxis
host wiring, ECPA activation, lifecycle/failure recovery, effect counters, exact
outputs, matched online ON/OFF services, and peak HBM remain required.
