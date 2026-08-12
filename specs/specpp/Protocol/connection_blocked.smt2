; Connection blocked must not be silently ignored — expected sat
(set-logic ALL)
(declare-datatypes () ((BlockedState (Clear) (Blocked) (Seen))))
(declare-fun state () BlockedState)
(declare-fun handled () Bool)

; Legal: blocked frame observed ⇒ handled
(assert (= state Blocked))
(assert handled)
(assert (=> (= state Blocked) handled))
(check-sat)
