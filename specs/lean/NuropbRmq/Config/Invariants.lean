/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Config.QueueProfile

/-!
Config invariants: durable never disagrees with persistent delivery_mode.
-/

namespace NuropbRmq.Config

theorem durable_requires_persistent (p : QueueProfile)
    (hd : p.durable = true) (hc : consistent p = true) :
    p.deliveryMode = 2 := by
  simp [consistent, hd] at hc
  exact hc.2

theorem transient_requires_non_persistent (p : QueueProfile)
    (hd : p.durable = false) (hc : consistent p = true) :
    p.deliveryMode = 1 := by
  simp [consistent, hd] at hc
  exact hc.2

theorem durableAtLeastOnce_consistent :
    consistent durableAtLeastOnce = true := by
  native_decide

theorem transientFastPath_consistent :
    consistent transientFastPath = true := by
  native_decide

theorem badDurableNonPersistent_inconsistent :
    consistent badDurableNonPersistent = false := by
  native_decide

theorem badTransientPersistent_inconsistent :
    consistent badTransientPersistent = false := by
  native_decide

/-- SpeC++ sat world: durable ∧ delivery_mode = 2 ∧ consistent. -/
theorem sat_world_durable_persistent :
    let p := durableAtLeastOnce
    p.durable = true ∧ p.deliveryMode = 2 ∧ consistent p = true := by
  native_decide

/-- SpeC++ unsat world: durable ∧ delivery_mode = 1 ∧ consistent is impossible. -/
theorem unsat_durable_non_persistent :
    ¬ (consistent badDurableNonPersistent = true) := by
  native_decide

end NuropbRmq.Config
