use std::hint::black_box;
use std::time::Instant;

use stateaxis_incremental_eviction::{BitmapEvictionIndex, EvictionFlags};

#[derive(Clone)]
struct ReferenceEntry {
    handle: String,
    generation: u64,
    utility: f64,
    last_access_ms: u64,
    flags: EvictionFlags,
}

fn percentile(mut values: Vec<u128>, numerator: usize, denominator: usize) -> u128 {
    values.sort_unstable();
    values[values.len() * numerator / denominator]
}

fn main() {
    const REPEATS: usize = 20_000;
    println!("records,victims,reference_p50_ns,reference_p95_ns,bitmap_p50_ns,bitmap_p95_ns");
    for records in [17_usize, 32, 64] {
        let mut source = Vec::with_capacity(records);
        let mut index = BitmapEvictionIndex::default();
        for i in 0..records {
            let flags = EvictionFlags {
                pinned: i % 13 == 0,
                pending: i % 17 == 0,
                soft_protected: i % 7 == 0,
            };
            let entry = ReferenceEntry {
                handle: format!("state-{i:02}"),
                generation: (i % 5) as u64,
                utility: ((i * 31) % 37) as f64 / 7.0,
                last_access_ms: ((i * 7_919) % 10_000) as u64,
                flags,
            };
            index
                .upsert(
                    entry.handle.clone(),
                    entry.generation,
                    entry.utility,
                    entry.last_access_ms,
                    entry.flags,
                )
                .unwrap();
            source.push(entry);
        }
        for victims in [1_usize, 4, 8] {
            let mut reference_samples = Vec::with_capacity(REPEATS);
            let mut bitmap_samples = Vec::with_capacity(REPEATS);
            for _ in 0..REPEATS {
                let start = Instant::now();
                let mut eligible: Vec<_> = source
                    .iter()
                    .filter(|entry| !entry.flags.pinned && !entry.flags.pending)
                    .collect();
                eligible.sort_by(|left, right| {
                    left.flags
                        .soft_protected
                        .cmp(&right.flags.soft_protected)
                        .then_with(|| left.utility.total_cmp(&right.utility))
                        .then_with(|| left.last_access_ms.cmp(&right.last_access_ms))
                        .then_with(|| left.handle.cmp(&right.handle))
                        .then_with(|| left.generation.cmp(&right.generation))
                });
                let selected: Vec<_> = eligible
                    .iter()
                    .take(victims)
                    .map(|entry| entry.handle.clone())
                    .collect();
                black_box(selected);
                reference_samples.push(start.elapsed().as_nanos());

                let start = Instant::now();
                black_box(index.preview(victims));
                bitmap_samples.push(start.elapsed().as_nanos());
            }
            println!(
                "{records},{victims},{},{},{},{}",
                percentile(reference_samples.clone(), 1, 2),
                percentile(reference_samples, 95, 100),
                percentile(bitmap_samples.clone(), 1, 2),
                percentile(bitmap_samples, 95, 100),
            );
        }
    }
}
