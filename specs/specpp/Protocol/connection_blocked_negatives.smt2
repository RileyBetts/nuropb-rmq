; Connection blocked silent-drop negative — expected unsat
(set-logic ALL)
(declare-datatypes () ((BlockedState (Clear) (Blocked))))
(declare-fun state () BlockedState)
(declare-fun handled () Bool)
(assert (= state Blocked))
(assert (not handled))
(assert (=> (= state Blocked) handled))
(check-sat)
