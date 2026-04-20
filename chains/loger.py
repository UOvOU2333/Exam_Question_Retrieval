import os
import logging

LOG_PATH = os.path.join(os.path.dirname(__file__), "agent.log")

logging.basicConfig(
    level=logging.INFO,  # 记录 INFO 及以上级别
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8'),
    ]
)

def trace(title: str, header: str, content: str, level: str = "info"):
    getattr(logging, level)(f"[{title}] {header} --> {content}")
