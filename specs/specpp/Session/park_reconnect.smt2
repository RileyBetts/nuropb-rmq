; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Park-and-retry: pending may survive disconnect; epoch bumps — expected sat
(set-logic ALL)
(declare-fun pending_before () Int)
(declare-fun pending_after_park_disconnect () Int)
(declare-fun reply_open_after_park () Bool)
(declare-fun epoch () Int)
(declare-fun epoch_after () Int)
(declare-fun reply_open_after_reconnect () Bool)
(declare-fun pending_after_reconnect () Int)
(declare-fun fail_outstanding () Bool)

(assert (not fail_outstanding))
(assert (= pending_before 2))
(assert (= pending_after_park_disconnect pending_before))
(assert (not reply_open_after_park))
(assert (= epoch_after (+ epoch 1)))
(assert reply_open_after_reconnect)
(assert (= pending_after_reconnect pending_after_park_disconnect))
(assert (>= pending_after_reconnect 0))
(check-sat)
