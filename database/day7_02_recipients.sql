USE bankpilot_day7_test;
-- No DDL needed: Day2 already has UNIQUE KEY uk_payees_user_account(user_id,payee_account_id).
-- Check uniqueness BEFORE installing the app:
SHOW INDEX FROM payees;
SELECT user_id,payee_account_id,COUNT(*) AS copies
  FROM payees GROUP BY user_id,payee_account_id HAVING COUNT(*)>1;
