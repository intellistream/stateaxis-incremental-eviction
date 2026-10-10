use std::hint::black_box;
use std::time::Instant;

use stateaxis_incremental_eviction::{BitmapEvictionIndex, EvictionFlags};

#[derive(Clone)]
struct ReferenceEntry {
    handle: String,
    generation: u64,
    value_density: f64,
    last_access_ms: u64,
    flags: EvictionFlags,
}

fn percentile(mut values: Vec<u128>, numerator: usize, denominator: usize) -> u128 {
    values.sort_unstable();
    values[values.len() * numerator / denominator]
}

fn main() {
    const REPEATS: usize = 20_000;
    const NOW_MS: u64 = 20_000;
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
                value_density: ((i * 31) % 37) as f64 / 7.0,
                last_access_ms: ((i * 7_919) % 10_000) as u64,
                flags,
            };
            index
                .upsert(
                    entry.handle.clone(),
                    entry.generation,
                    entry.value_density,
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
                    .map(|entry| {
                        let age_s = ((NOW_MS - entry.last_access_ms) as f64 / 1000.0).max(1.0);
                        (entry, entry.value_density / age_s.sqrt())
                    })
                    .collect();
                eligible.sort_by(|left, right| {
                    left.0
                        .flags
                        .soft_protected
                        .cmp(&right.0.flags.soft_protected)
                        .then_with(|| left.1.total_cmp(&right.1))
                        .then_with(|| left.0.last_access_ms.cmp(&right.0.last_access_ms))
                        .then_with(|| left.0.handle.cmp(&right.0.handle))
                        .then_with(|| left.0.generation.cmp(&right.0.generation))
                });
                let selected: Vec<_> = eligible
                    .iter()
                    .take(victims)
                    .map(|entry| entry.0.handle.clone())
                    .collect();
                black_box(selected);
                reference_samples.push(start.elapsed().as_nanos());

                let start = Instant::now();
                black_box(index.preview_at(victims, NOW_MS));
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
