//! Bounded, generation-safe eviction index for small resident-state sets.
//!
//! The index incrementally maintains at most 64 stable slots and one eligibility
//! bitmap. Victim preview scans only set bits and allocates only the returned
//! handles; it does not clone the index or sort all records.

use std::cmp::Ordering;
use std::collections::HashMap;

pub const MAX_BITMAP_STATES: usize = u64::BITS as usize;

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct EvictionFlags {
    pub pinned: bool,
    pub pending: bool,
    pub soft_protected: bool,
}

#[derive(Clone, Debug)]
struct Entry {
    handle: String,
    generation: u64,
    value_density: f64,
    last_access_ms: u64,
    soft_protected: bool,
}

impl Entry {
    fn utility_at(&self, now_ms: u64) -> f64 {
        let age_s = ((now_ms.saturating_sub(self.last_access_ms)) as f64 / 1000.0).max(1.0);
        self.value_density / age_s.sqrt()
    }

    fn eviction_cmp_at(&self, other: &Self, now_ms: u64) -> Ordering {
        self.eviction_cmp_with_scores(self.utility_at(now_ms), other, other.utility_at(now_ms))
    }

    fn eviction_cmp_with_scores(&self, utility: f64, other: &Self, other_utility: f64) -> Ordering {
        self.soft_protected
            .cmp(&other.soft_protected)
            .then_with(|| utility.total_cmp(&other_utility))
            .then_with(|| self.last_access_ms.cmp(&other.last_access_ms))
            .then_with(|| self.handle.cmp(&other.handle))
            .then_with(|| self.generation.cmp(&other.generation))
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct CapacityError {
    pub capacity: usize,
}

/// Incrementally updated eviction authority for at most 64 live states.
#[derive(Clone, Debug, Default)]
pub struct BitmapEvictionIndex {
    slots: Vec<Option<Entry>>,
    by_handle: HashMap<String, usize>,
    eligible: u64,
}

impl BitmapEvictionIndex {
    /// Return `None` when bulk eviction should use the existing full-sort
    /// authority. The bitmap path is intentionally limited to the region in
    /// which its bounded scan wins the measured crossover.
    pub fn preview_bounded_at(&self, max_states: usize, now_ms: u64) -> Option<Vec<String>> {
        (max_states <= 1).then(|| self.preview_at(max_states, now_ms))
    }

    pub fn upsert(
        &mut self,
        handle: impl Into<String>,
        generation: u64,
        value_density: f64,
        last_access_ms: u64,
        flags: EvictionFlags,
    ) -> Result<(), CapacityError> {
        let handle = handle.into();
        let slot = if let Some(&slot) = self.by_handle.get(&handle) {
            slot
        } else if let Some(slot) = self.slots.iter().position(Option::is_none) {
            self.by_handle.insert(handle.clone(), slot);
            slot
        } else if self.slots.len() < MAX_BITMAP_STATES {
            let slot = self.slots.len();
            self.slots.push(None);
            self.by_handle.insert(handle.clone(), slot);
            slot
        } else {
            return Err(CapacityError {
                capacity: MAX_BITMAP_STATES,
            });
        };

        self.slots[slot] = Some(Entry {
            handle,
            generation,
            value_density,
            last_access_ms,
            soft_protected: flags.soft_protected,
        });
        let bit = 1_u64 << slot;
        if flags.pinned || flags.pending {
            self.eligible &= !bit;
        } else {
            self.eligible |= bit;
        }
        Ok(())
    }

    /// Refresh a known generation without allocating or replacing its handle.
    /// Returns false for unknown or stale identities so callers can fail closed
    /// or perform an explicit generation replacement through `upsert`.
    pub fn refresh(
        &mut self,
        handle: &str,
        generation: u64,
        value_density: f64,
        last_access_ms: u64,
        flags: EvictionFlags,
    ) -> bool {
        let Some(&slot) = self.by_handle.get(handle) else {
            return false;
        };
        let Some(entry) = self.slots[slot].as_mut() else {
            return false;
        };
        if entry.generation != generation {
            return false;
        }
        entry.value_density = value_density;
        entry.last_access_ms = last_access_ms;
        entry.soft_protected = flags.soft_protected;
        let bit = 1_u64 << slot;
        if flags.pinned || flags.pending {
            self.eligible &= !bit;
        } else {
            self.eligible |= bit;
        }
        true
    }

    pub fn invalidate(&mut self, handle: &str, generation: u64) -> bool {
        let Some(&slot) = self.by_handle.get(handle) else {
            return false;
        };
        let Some(entry) = self.slots[slot].as_ref() else {
            return false;
        };
        if entry.generation != generation {
            return false;
        }
        self.by_handle.remove(handle);
        self.slots[slot] = None;
        self.eligible &= !(1_u64 << slot);
        true
    }

    fn victim_slot_at(&self, bitmap: u64, now_ms: u64) -> Option<usize> {
        let mut remaining = bitmap;
        let mut victim: Option<usize> = None;
        let mut victim_utility = 0.0;
        while remaining != 0 {
            let slot = remaining.trailing_zeros() as usize;
            remaining &= remaining - 1;
            let entry = self.slots[slot]
                .as_ref()
                .expect("eligible bit must reference a live slot");
            let utility = entry.utility_at(now_ms);
            if victim.is_none_or(|current| {
                entry.eviction_cmp_with_scores(
                    utility,
                    self.slots[current]
                        .as_ref()
                        .expect("selected victim must remain live"),
                    victim_utility,
                ) == Ordering::Less
            }) {
                victim = Some(slot);
                victim_utility = utility;
            }
        }
        victim
    }

    pub fn preview_at(&self, max_states: usize, now_ms: u64) -> Vec<String> {
        if max_states > 4 {
            return self.preview_many_at(max_states, now_ms);
        }
        let mut remaining = self.eligible;
        let mut victims = Vec::with_capacity(max_states.min(remaining.count_ones() as usize));
        while victims.len() < max_states {
            let Some(slot) = self.victim_slot_at(remaining, now_ms) else {
                break;
            };
            victims.push(
                self.slots[slot]
                    .as_ref()
                    .expect("selected victim must remain live")
                    .handle
                    .clone(),
            );
            remaining &= !(1_u64 << slot);
        }
        victims
    }

    fn preview_many_at(&self, max_states: usize, now_ms: u64) -> Vec<String> {
        let mut slots = [0_usize; MAX_BITMAP_STATES];
        let mut len = 0;
        let mut remaining = self.eligible;
        while remaining != 0 {
            slots[len] = remaining.trailing_zeros() as usize;
            len += 1;
            remaining &= remaining - 1;
        }
        let compare = |left: &usize, right: &usize| {
            self.slots[*left]
                .as_ref()
                .expect("eligible bit must reference a live slot")
                .eviction_cmp_at(
                    self.slots[*right]
                        .as_ref()
                        .expect("eligible bit must reference a live slot"),
                    now_ms,
                )
        };
        let selected = len.min(max_states);
        if selected < len {
            slots[..len].select_nth_unstable_by(selected, compare);
        }
        slots[..selected].sort_unstable_by(compare);
        slots[..selected]
            .iter()
            .map(|slot| {
                self.slots[*slot]
                    .as_ref()
                    .expect("selected victim must remain live")
                    .handle
                    .clone()
            })
            .collect()
    }

    pub fn pop_victim_at(&mut self, now_ms: u64) -> Option<String> {
        let slot = self.victim_slot_at(self.eligible, now_ms)?;
        let entry = self.slots[slot]
            .take()
            .expect("selected victim must remain live");
        self.by_handle.remove(&entry.handle);
        self.eligible &= !(1_u64 << slot);
        Some(entry.handle)
    }

    pub fn len(&self) -> usize {
        self.by_handle.len()
    }

    pub fn is_empty(&self) -> bool {
        self.by_handle.is_empty()
    }

    pub fn eligible_len(&self) -> usize {
        self.eligible.count_ones() as usize
    }
}

#[cfg(test)]
mod tests {
    use super::{BitmapEvictionIndex, EvictionFlags, MAX_BITMAP_STATES};

    fn flags(pinned: bool, pending: bool, soft_protected: bool) -> EvictionFlags {
        EvictionFlags {
            pinned,
            pending,
            soft_protected,
        }
    }

    #[test]
    fn bitmap_order_matches_full_sort_reference() {
        const NOW_MS: u64 = 20_000;
        let mut index = BitmapEvictionIndex::default();
        let mut reference = Vec::new();
        let mut state = 0x9e37_79b9_u64;
        for i in 0..MAX_BITMAP_STATES {
            state = state
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1);
            let value_density = ((state >> 11) % 37) as f64 / 7.0;
            let last_access_ms = (state >> 19) % 10_000;
            let entry_flags = flags(i % 13 == 0, i % 17 == 0, i % 7 == 0);
            let handle = format!("state-{i:02}");
            index
                .upsert(
                    handle.clone(),
                    (i % 5) as u64,
                    value_density,
                    last_access_ms,
                    entry_flags,
                )
                .unwrap();
            if !entry_flags.pinned && !entry_flags.pending {
                reference.push((
                    entry_flags.soft_protected,
                    value_density / (((NOW_MS - last_access_ms) as f64 / 1000.0).max(1.0)).sqrt(),
                    last_access_ms,
                    handle,
                    (i % 5) as u64,
                ));
            }
        }
        reference.sort_by(|left, right| {
            left.0
                .cmp(&right.0)
                .then_with(|| left.1.total_cmp(&right.1))
                .then_with(|| left.2.cmp(&right.2))
                .then_with(|| left.3.cmp(&right.3))
                .then_with(|| left.4.cmp(&right.4))
        });
        let expected: Vec<_> = reference.into_iter().map(|row| row.3).collect();
        assert_eq!(index.preview_at(MAX_BITMAP_STATES, NOW_MS), expected);
    }

    #[test]
    fn generation_guard_and_slot_reuse_are_fail_closed() {
        let mut index = BitmapEvictionIndex::default();
        index
            .upsert("same", 1, 0.1, 1, flags(false, false, false))
            .unwrap();
        index
            .upsert("same", 2, 10.0, 2, flags(false, false, false))
            .unwrap();
        assert!(!index.invalidate("same", 1));
        assert_eq!(index.preview_at(1, 1_000), ["same"]);
        assert!(index.invalidate("same", 2));
        index
            .upsert("replacement", 1, 1.0, 3, flags(false, false, false))
            .unwrap();
        assert_eq!(index.pop_victim_at(1_000).as_deref(), Some("replacement"));
        assert!(index.is_empty());
    }

    #[test]
    fn eligibility_updates_do_not_leave_stale_bits() {
        let mut index = BitmapEvictionIndex::default();
        index
            .upsert("state", 1, 1.0, 1, flags(false, false, false))
            .unwrap();
        assert_eq!(index.eligible_len(), 1);
        index
            .upsert("state", 1, 1.0, 1, flags(true, false, false))
            .unwrap();
        assert_eq!(index.eligible_len(), 0);
        assert!(index.preview_at(1, 1_000).is_empty());
        index
            .upsert("state", 1, 1.0, 1, flags(false, false, true))
            .unwrap();
        assert_eq!(index.preview_at(1, 1_000), ["state"]);
    }

    #[test]
    fn refresh_is_generation_checked_and_reorders_without_handle_replacement() {
        let mut index = BitmapEvictionIndex::default();
        index
            .upsert("first", 2, 1.0, 1, flags(false, false, false))
            .unwrap();
        index
            .upsert("second", 1, 2.0, 2, flags(false, false, false))
            .unwrap();
        assert!(!index.refresh("first", 1, 9.0, 9, flags(false, false, false)));
        assert!(index.refresh("first", 2, 3.0, 3, flags(false, false, false)));
        assert_eq!(index.preview_at(2, 1_000), ["second", "first"]);
        assert!(index.refresh("second", 1, 0.0, 0, flags(true, false, false)));
        assert_eq!(index.preview_at(2, 1_000), ["first"]);
    }

    #[test]
    fn sixty_fifth_live_state_fails_without_partial_insert() {
        let mut index = BitmapEvictionIndex::default();
        for i in 0..MAX_BITMAP_STATES {
            index
                .upsert(
                    format!("state-{i}"),
                    1,
                    i as f64,
                    i as u64,
                    EvictionFlags::default(),
                )
                .unwrap();
        }
        let error = index
            .upsert("overflow", 1, 0.0, 0, EvictionFlags::default())
            .unwrap_err();
        assert_eq!(error.capacity, MAX_BITMAP_STATES);
        assert_eq!(index.len(), MAX_BITMAP_STATES);
        assert_eq!(index.preview_at(1, 1_000), ["state-0"]);
    }

    #[test]
    fn bulk_selection_explicitly_falls_back_to_full_sort() {
        let mut index = BitmapEvictionIndex::default();
        for i in 0..17 {
            index
                .upsert(
                    format!("state-{i}"),
                    1,
                    i as f64,
                    i,
                    EvictionFlags::default(),
                )
                .unwrap();
        }
        assert!(index.preview_bounded_at(0, 1_000).unwrap().is_empty());
        assert_eq!(index.preview_bounded_at(1, 1_000).unwrap().len(), 1);
        assert!(index.preview_bounded_at(2, 1_000).is_none());
    }
}
