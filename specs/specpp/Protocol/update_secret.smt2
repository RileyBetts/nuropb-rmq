; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; connection.update-secret legal only from OPEN_OK — expected sat
(set-logic ALL)
(declare-datatypes () ((ConnState (Init) (Start) (OpenOk) (Closing) (Error))))
(declare-fun conn () ConnState)
(declare-fun legal_update_secret () Bool)
(assert (= conn OpenOk))
(assert (= legal_update_secret (= conn OpenOk)))
(assert legal_update_secret)
(check-sat)
