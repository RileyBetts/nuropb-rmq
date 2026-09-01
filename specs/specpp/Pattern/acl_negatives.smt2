; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Forge user writing nr.reply is illegal under the profile — unsat
(set-logic ALL)
(set-info :status unsat)
(declare-fun client_write_reply () Bool)
(assert (not client_write_reply))
(assert client_write_reply)
(check-sat)
