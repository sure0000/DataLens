# 测试数据：会员与积分域

## 文件

| 文件 | 用途 |
|------|------|
| `member_crm_mysql.sql` | 建库 `retail_ops`、三张表及样例数据；**先导入**。 |
| `knowledge_member_crm_domain.md` | 业务口径与表说明；拆成知识库条目，**表分析完成后再导入**以便对比 RAG 效果。 |

## 导入步骤（简）

1. MySQL：`mysql -h... -u... -p < scripts/testdata/member_crm_mysql.sql`
2. DataLens：新增数据源指向 `retail_ops`，**测试连接 → 分析库表**。
3. 业务域：挂载库 `retail_ops` 及三张表；Copilot 选该域，先不配知识库，测选表。
4. 将 `knowledge_member_crm_domain.md` 拆成条目写入已绑定到该域的知识库，再测问答口径。
