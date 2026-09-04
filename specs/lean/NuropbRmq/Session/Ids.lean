/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
Correlation id charset + length (AMQP shortstr bound). Python `session.ids`.
-/

namespace NuropbRmq.Session.Ids

def validIdLen (n : Nat) : Bool :=
  decide (1 ≤ n ∧ n ≤ 255)

def isSafeChar (c : Char) : Bool :=
  c.isAlphanum || c == '.' || c == '_' || c == ':' || c == '-'

def validId (s : String) : Bool :=
  let n := s.toUTF8.size
  validIdLen n && s.all isSafeChar

end NuropbRmq.Session.Ids
