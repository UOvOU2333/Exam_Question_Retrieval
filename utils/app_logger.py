"""统一应用日志模块。

设计要点：
  - 基于 Python 标准库 logging，RotatingFileHandler 防止日志文件无限增长
  - 同时输出到文件（logs/app.log）和 stdout（服务器 systemd 日志可捕获）
  - 按模块分 logger，便于定位问题来源
  - 提供 measure_time 上下文管理器测量耗时（诊断卡死高嫌疑的 API 调用）
  - 全局只初始化一次，多次调用 get_logger 安全

日志文件位置：项目根目录 logs/app.log（单文件 10MB，保留 5 个备份）
"""
import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
from contextlib import contextmanager

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

_initialized = False


def _init_root_logger():
    """初始化根 logger，全局只执行一次。"""
    global _initialized
    if _initialized:
        return
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
    except Exception:
        pass

    root = logging.getLogger("eqr")
    if root.handlers:
        _initialized = True
        return

    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        _LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    root.propagate = False
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取按模块命名的 logger。

    Args:
        name: 模块名，建议传 __name__ 或简短标识（如 "auth"、"record_agent"）

    Returns:
        logging.Logger 实例
    """
    _init_root_logger()
    if not name.startswith("eqr"):
        name = "eqr.%s" % name
    return logging.getLogger(name)


@contextmanager
def measure_time(logger: logging.Logger, action: str, level=logging.INFO, **extra):
    """测量代码块耗时的上下文管理器。

    用法：
        with measure_time(log, "deepseek_api_call", model="deepseek-chat"):
            resp = requests.post(...)

    结束时自动记录耗时；若块内抛异常，记录 ERROR 级别并附带异常信息。
    """
    start = time.time()
    extra_str = " ".join("%s=%s" % (k, v) for k, v in extra.items())
    logger.log(level, "START %s %s", action, extra_str)
    try:
        yield
    except Exception as e:
        elapsed = time.time() - start
        logger.error(
            "FAIL %s elapsed=%.2fs error=%s: %s %s",
            action, elapsed, type(e).__name__, e, extra_str,
        )
        raise
    else:
        elapsed = time.time() - start
        logger.log(level, "END %s elapsed=%.2fs %s", action, elapsed, extra_str)
