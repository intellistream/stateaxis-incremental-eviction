# Issue #10 incremental eviction closure

Status: **closed negative; experimental candidate not promoted**.

The frozen matched NPU run set contains three control and three candidate runs on
the same NPU, image, binary, oracle, client and workload identity. Every run made
128 eviction decisions, selected 128 victims, passed 128 replacement and pressure
checks, rejected 128 stale generations, and recorded zero fallback, mismatch,
rebuild or stale-pop events.

The isolated candidate selector was slower than the full-sort reference at the
measured 17-state serving capacity: median run p50/p95 was
93248/95527 ns versus
27648/30516 ns, or
3.373x/3.130x slower.
The candidate was therefore not promoted and full-sort remains authoritative.

Request-level recomputation gives all-operation control p50/p95
136.310/3427.431 ms at
10.1644 HTTP operations/s and candidate
136.564/3401.417 ms at
10.1413 HTTP operations/s. The successful
inference subset is 5.2455 versus
5.2336 requests/s. The endpoint
deltas are mixed and no end-to-end superiority claim is made.

## Aggregation correction

The historical summary reported approximately 1.593 and
1.600 requests/s by dividing request count by the sum of all
per-request latencies. That denominator is invalid because the 128 pressure
requests overlap. This closure uses the sum of per-run observed wall intervals,
`max(completed_ns) - min(started_ns)`, yielding the values above. The rejected
calculation is retained in `rejected_aggregation.json`.

`requests.jsonl` is the normalized request-level raw evidence; `runs.jsonl`
preserves per-run metrics and SHA-256 links to the original artifacts. The tested
candidate was an experimental, default-off production-bound path and was never
merged as current production authority. The repository's current authority is
therefore accurately described as full-sort, with the component/shadow retained
for research only.
