"""TG-Chat-to-SQL 核心层（V1.2.0）。

模块划分：
- paths        应用数据目录与默认路径
- logging_setup 轮转日志
- db           SQLite Schema v3（多群、复合索引）
- importer     流式增量导入
- backup       快照、校验、恢复、保留策略
- security     删除权限闸门与审计
- server       本地 HTTP API
"""

__version__ = "1.2.0"
