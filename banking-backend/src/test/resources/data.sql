INSERT INTO users (id, display_name) VALUES (1, '张小明'), (2, '李四');
INSERT INTO accounts (id, user_id, account_no, balance, status) VALUES
 (1, 1, 'DEMO-6688', 12580.50, 'ACTIVE'),
 (2, 2, 'DEMO-5291', 5000.00, 'ACTIVE');
INSERT INTO transactions (account_id, direction, amount, category, merchant_name, description, occurred_at) VALUES
 (1, 'IN', 8000.00, '工资', '公司', '十月工资', '2026-10-03 09:00:00'),
 (1, 'OUT', 35.00, '餐饮', '美团外卖', '午餐', '2026-10-05 12:00:00'),
 (1, 'OUT', 25.00, '订阅', '视频会员', '会员自动扣费', '2026-10-08 08:00:00'),
 (2, 'OUT', 999.00, '购物', '其他用户商户', '不可见', '2026-10-09 08:00:00');
INSERT INTO payees (id, user_id, payee_name, payee_account_id) VALUES
 (1, 1, '李四', 2), (2, 2, '张小明', 1);
INSERT INTO subscriptions (id, user_id, merchant_name, amount, billing_cycle, status, next_pay_date) VALUES
 (1, 1, '视频会员', 25.00, 'MONTHLY', 'ACTIVE', '2026-11-08'),
 (2, 1, '音乐会员', 15.00, 'MONTHLY', 'ACTIVE', '2026-11-12'),
 (3, 2, '其他用户会员', 199.00, 'MONTHLY', 'ACTIVE', '2026-11-20');
