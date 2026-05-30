-- 订单与明细 JOIN，并写入汇总表
INSERT INTO dwd_order_summary
SELECT o.id, o.user_id, SUM(i.amount) AS total
FROM orders o
INNER JOIN order_items i ON o.id = i.order_id
GROUP BY o.id, o.user_id;

CREATE TABLE dwd_user_orders AS
SELECT u.id, COUNT(o.id) AS order_cnt
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id;
