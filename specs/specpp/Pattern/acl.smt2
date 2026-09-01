; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; reply-publish-restricted: forge cannot write nr.reply.* — sat model
(set-logic ALL)
(declare-fun client_write_reply () Bool)
(declare-fun service_write_reply () Bool)
(assert (not client_write_reply))
(assert service_write_reply)
(assert (=> client_write_reply false))
(check-sat)
