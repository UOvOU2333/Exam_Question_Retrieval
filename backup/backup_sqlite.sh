#!/bin/bash

# 配置参数
DB_PATH="data/questions.db"   # SQLite 数据库文件路径
BACKUP_DIR="backup"   # 备份存放目录
RETENTION_DAYS=30   # 保留最近几天的备份

# 生成备份文件名（按日期）
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/db_backup_$DATE.db"

# 使用 sqlite3 的 .backup 命令进行在线一致备份
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# 可选：压缩备份文件（节省空间）
gzip "$BACKUP_FILE"

# 删除超过 RETENTION_DAYS 天的旧备份（注意压缩后的 .gz 文件）
find "$BACKUP_DIR" -name "db_backup_*.db.gz" -type f -mtime +$RETENTION_DAYS -delete

# 可选：记录日志
echo "$(date): Backup created at $BACKUP_FILE.gz" >> "$BACKUP_DIR/backup.log"