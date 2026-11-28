-- D14 isolated demo database only. Run after selecting bankpilot_day7_test.
USE bankpilot_day7_test;
-- A: one registered card must correspond to exactly one successful application.
SELECT c.id AS card_id, c.user_id, COUNT(a.id) AS issued_application_count
FROM demo_virtual_cards c
LEFT JOIN demo_card_applications a
  ON a.card_id=c.id AND a.user_id=c.user_id AND a.status='ISSUED'
GROUP BY c.id,c.user_id
HAVING issued_application_count <> 1;
-- B: no ISSUED application may lack a valid owner's card.
SELECT a.id AS application_id,a.user_id,a.card_id
FROM demo_card_applications a
LEFT JOIN demo_virtual_cards c ON c.id=a.card_id AND c.user_id=a.user_id
WHERE a.status='ISSUED' AND c.id IS NULL;
-- C: pending or cancelled applications must not reference a card.
SELECT id,user_id,status,card_id
FROM demo_card_applications
WHERE status IN ('PENDING_APPROVAL','CANCELLED') AND card_id IS NOT NULL;
-- D: no invalid card limits/status.
SELECT id,user_id,daily_ceiling,single_tx_limit,status
FROM demo_virtual_cards
WHERE single_tx_limit<=0 OR single_tx_limit>daily_ceiling
   OR status NOT IN ('ACTIVE','LOCKED','LOST');
-- E: read-only summary for screenshots.
SELECT user_id, COUNT(*) AS simulated_card_count
FROM demo_virtual_cards GROUP BY user_id ORDER BY user_id;
SELECT card_id,COUNT(*) AS restriction_change_count
FROM demo_card_limit_events GROUP BY card_id ORDER BY card_id;
