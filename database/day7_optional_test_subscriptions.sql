-- OPTIONAL: Day7 demo-only subscription seed; run manually on TEST database after registering zhangsan.
-- Keeps all existing subscriptions and Day6 cancellation history untouched.
-- No hard-coded user ID, no update of already-cancelled subscriptions.
SELECT DATABASE() AS active_schema;
INSERT INTO subscriptions(user_id,merchant_name,amount,billing_cycle,status,next_pay_date,cancelled_at)
SELECT c.user_id,'视频会员',25.00,'MONTHLY','ACTIVE',DATE_ADD(CURDATE(),INTERVAL 30 DAY),NULL
FROM user_credentials c
WHERE c.username='zhangsan' AND NOT EXISTS (
 SELECT 1 FROM subscriptions s WHERE s.user_id=c.user_id AND s.merchant_name='视频会员');
INSERT INTO subscriptions(user_id,merchant_name,amount,billing_cycle,status,next_pay_date,cancelled_at)
SELECT c.user_id,'音乐会员',15.00,'MONTHLY','ACTIVE',DATE_ADD(CURDATE(),INTERVAL 30 DAY),NULL
FROM user_credentials c
WHERE c.username='zhangsan' AND NOT EXISTS (
 SELECT 1 FROM subscriptions s WHERE s.user_id=c.user_id AND s.merchant_name='音乐会员');
