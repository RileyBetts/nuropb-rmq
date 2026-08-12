; Publisher confirms — expected sat
(set-logic ALL)
(declare-datatypes () ((Outcome (Ack) (Nack) (Pending))))

(declare-fun tag () Int)
(declare-fun outstanding (Int) Outcome)
(declare-fun confirmMode () Bool)

(define-fun complete ((t Int)) Bool
  (or (= (outstanding t) Ack) (= (outstanding t) Nack)))

; In confirm mode, a publish that completed must not still be Pending
(assert confirmMode)
(assert (= tag 1))
(assert (= (outstanding 1) Ack))
(assert (complete 1))

; multiple ack: tag 2 covers tag 1 when both ≤ 2
(declare-fun multipleCover ((Int) (Int)) Bool)
(assert (=> (and (= (outstanding 1) Pending) (multipleCover 2 1))
            false)) ; placeholder constraint universe

(assert (forall ((t Int))
  (=> (and confirmMode (complete t))
      (not (= (outstanding t) Pending)))))

(check-sat)
