# get_db_schema_fixed.py
"""
获取SQLite数据库完整结构的Python脚本（已修复KeyError问题）。
运行命令：python get_db_schema_fixed.py
"""

import sqlite3
import json
from pathlib import Path

def get_database_schema(db_path: str) -> dict:
    """
    获取SQLite数据库的完整结构。
    返回一个包含表、列、索引和外键信息的字典。
    """
    schema = {
        "database_path": db_path,
        "tables": {},
        "indexes": [],
        "foreign_keys": []
    }
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 以字典形式返回行
    cursor = conn.cursor()
    
    # 1. 获取所有用户表的基本信息
    cursor.execute("""
        SELECT name, sql 
        FROM sqlite_master 
        WHERE type='table' 
            AND name NOT LIKE 'sqlite_%'
    """)
    
    tables = cursor.fetchall()
    
    for table in tables:
        table_name = table['name']
        table_ddl = table['sql']
        
        # 2. 获取表的列信息
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        column_details = []
        for col in columns:
            # 关键修正：使用正确的键名从sqlite3.Row对象中提取数据
            column_details.append({
                "cid": col['cid'],
                "name": col['name'],
                "type": col['type'],
                "notnull": bool(col['notnull']),
                "dflt_value": col['dflt_value'],  # 注意：列名是 'dflt_value'
                "pk": bool(col['pk'])
            })
        
        # 3. 获取表的外键约束信息
        cursor.execute(f"PRAGMA foreign_key_list({table_name})")
        fks = cursor.fetchall()
        
        foreign_keys = []
        for fk in fks:
            foreign_keys.append({
                "id": fk['id'],
                "seq": fk['seq'],
                "from_table": table_name,
                "from_column": fk['from'],
                "to_table": fk['to'],
                "to_column": fk['to']
            })
            # 收集到全局外键列表
            schema["foreign_keys"].append({
                "table": table_name,
                "constraint": dict(fk)  # 将Row转换为字典以便于JSON序列化
            })
        
        # 4. 获取表的索引信息
        cursor.execute(f"PRAGMA index_list({table_name})")
        idx_list = cursor.fetchall()
        
        table_indexes = []
        for idx in idx_list:
            if idx['origin'] != 'pk':  # 排除主键索引
                cursor.execute(f"PRAGMA index_info({idx['name']})")
                idx_cols = cursor.fetchall()
                table_indexes.append({
                    "name": idx['name'],
                    "unique": bool(idx['unique']),
                    "columns": [col['name'] for col in idx_cols]
                })
                # 收集到全局索引列表
                schema["indexes"].append({
                    "table": table_name,
                    "index": idx['name'],
                    "columns": [col['name'] for col in idx_cols]
                })
        
        # 将表信息存入schema
        schema["tables"][table_name] = {
            # "ddl": table_ddl,
            "columns": column_details,  # 这里存储的是自定义字典列表
            "foreign_keys": foreign_keys,
            "indexes": table_indexes
        }
    
    conn.close()
    return schema

def save_schema_to_file(schema: dict, output_path: str):
    """将数据库结构保存为JSON文件，便于分析和后续使用。"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"数据库结构已保存至: {output_path}")

def print_schema_summary(schema: dict):
    """打印数据库结构的摘要信息。"""
    print("="*60)
    print(f"数据库路径: {schema['database_path']}")
    print(f"表数量: {len(schema['tables'])}")
    print("="*60)
    
    for table_name, table_info in schema['tables'].items():
        print(f"\n表名: {table_name}")
        # 安全地截取DDL，避免NoneType错误
        # ddl_preview = (table_info['ddl'][:100] + '...') if table_info['ddl'] and len(table_info['ddl']) > 100 else (table_info['ddl'] or '')
        # print(f"DDL: {ddl_preview}")
        
        print("列信息:")
        # 关键修正：这里访问的是column_details列表中的字典，其键为'dflt_value'
        for col in table_info['columns']:
            pk_flag = " (主键)" if col['pk'] else ""
            nn_flag = " NOT NULL" if col['notnull'] else ""
            # 使用正确的键名 'dflt_value'
            default = f" DEFAULT {col['dflt_value']}" if col['dflt_value'] is not None else ""
            print(f"  - {col['name']}: {col['type']}{pk_flag}{nn_flag}{default}")
        
        if table_info['foreign_keys']:
            print("外键约束:")
            for fk in table_info['foreign_keys']:
                print(f"  - {fk['from_column']} -> {fk['to_table']}.{fk['to_column']}")
        
        if table_info['indexes']:
            print("索引:")
            for idx in table_info['indexes']:
                unique = "唯一" if idx['unique'] else "非唯一"
                print(f"  - {idx['name']} ({unique}): {', '.join(idx['columns'])}")
    
    print("\n" + "="*60)
    print("ER关系摘要:")
    if schema['foreign_keys']:
        for fk_info in schema['foreign_keys']:
            # fk_info['constraint'] 现在是一个字典
            constraint = fk_info['constraint']
            print(f"{fk_info['table']}.{constraint['from']} -> {constraint['to']}.{constraint['to']}")
    else:
        print("未检测到外键约束。")

if __name__ == "__main__":
    # 配置
    DB_PATH = "data/questions.db"  # 替换为您的数据库路径
    OUTPUT_JSON = "data/db_schema.json"
    
    # 获取结构
    print("正在分析数据库结构...")
    schema = get_database_schema(DB_PATH)
    
    # 打印摘要
    print_schema_summary(schema)
    
    # 保存为JSON
    save_schema_to_file(schema, OUTPUT_JSON)
