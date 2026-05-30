package com.example.mapper;

import org.apache.ibatis.annotations.Select;

public interface OrderMapper {

    @Select("SELECT o.id, i.product_id FROM orders o INNER JOIN order_items i ON o.id = i.order_id WHERE o.status = 'paid'")
    List<OrderItemRow> findPaidOrderItems();
}
