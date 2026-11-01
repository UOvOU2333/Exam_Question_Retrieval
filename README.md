# 高中政治题库系统（EQR）

基于 Streamlit、SQLite 的高中政治试题管理项目，提供检索、题目录入与编辑、备注、整卷导出、用户权限和 DeepSeek 智能助手。仓库另保留独立的审稿经验库及旧版 LangChain/RAG 实现。

本文依据当前代码更新。全仓静态审计范围、已复现问题与修复建议见 [代码审计记录](docs/CODE_AUDIT.md)。功能存在不代表所有路径均已通过端到端验收。

## 当前功能

主入口 `main.py` 的侧栏包含试题检索、试卷导出、智能助手和用户中心；顶部“管理”跳转到 `pages/managingPage.py`。

| 模块 | 当前实现 |
| --- | --- |
| 试题检索 | 年份多选、卷种、题号、关键词、题型、知识模块、新教材筛选；基础和高级模式 |
| 高级检索 | 备注标签、内容、创建人检索，与基础条件求交集；空条件与删除状态存在已知问题 |
| 详情显示 | 原生折叠框按展开状态加载正文、答案、解析、图片及可见备注；复制模式、关键词高亮 |
| 题目管理 | 上传、更新、Markdown 预览、图片上传、表格代码生成；解析可一键填“暂无”，提交后保存 |
| 题型 | 单项选择题、不定项选择题、填空题、缺项选择题、非选择题、判断题 |
| 知识模块 | 必修一至必修四、选必一至选必三，可多选；AI 推荐及离线回填 |
| 备注 | 类型管理、按角色设置可见范围；类型软删除/恢复、备注添加/软删除 |
| 试卷导出 | 按年份与卷种导出 Word（`.docx`）或 PDF，可选择答案、解析、来源；不含备注 |
| 卷种变更 | 管理员维护 JSON 规则，按年份和卷种精确匹配，批量更新非回收站题目 |
| 账号管理 | 登录、自助改名/改密码；管理员管理账号、角色、禁用状态和 AI 白名单 |
| 回收站 | 恢复、彻底删除、图片清理；权限与图片删除存在待修复问题 |

题型识别只是预填建议：题首明确标识优先，单个 A–D 字母默认单项，多字母无法确定时留空；应人工核对。“新教材”使用 `tools/exam_type_utils.py` 中的本地名单：2025 年及以后全部匹配，2022–2024 年按卷种匹配，更早年份不匹配，并非在线更新。

### 按需渲染

检索**没有分页**，全部结果标题连续展示。元信息批量读取，关闭的题目不加载正文、图片和备注。每 50 条组成一个内部 fragment，展开时只重跑所在分组；组间让出 20ms 供消息发送，降低大量折叠框挤满 WebSocket 队列的风险，不增加可见控件。

大量标题、多题同时展开和慢速连接仍可能增加负载；固定节流不是通用的网络背压机制。回收站等页面尚未同步采用这套加载方式。

## 环境与安装

从仓库根目录启动主站；其数据库和图片路径多数相对于当前工作目录。

本地检查环境为 Python 3.14、Streamlit 1.66.1、streamlit-antd-components 0.3.2。此 Streamlit 版本要求 Python 3.11+；当前代码使用 expander 的 `on_change` / `.open` 和 fragment，不能直接退回旧版。

仓库没有 `requirements.txt`、依赖锁文件或完整自动化测试套件。以下为按当前导入整理的安装起点，**不是经过完整干净环境验收的锁定依赖集**：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install "streamlit==1.66.1" "streamlit-antd-components==0.3.2" Pillow pandas requests Markdown watchdog python-docx htmldocx fpdf2
```

Linux/macOS 激活命令为 `source .venv/bin/activate`。Word 使用 `python-docx`、`htmldocx`；PDF 使用 **fpdf2**，不是旧的 `fpdf` 发行包。审稿库另需 SQLAlchemy，历史 RAG 依赖见后文。

PDF 还需要中文字体；候选路径位于 `utils/export_utils.py`。缺少字体时需安装或修改路径。图片、表格有专门转换，LaTeX 未提供专用的 Word/PDF 公式转换链路。

## 数据库准备与升级

### 已有完整数据库

主站数据库为 `data/questions.db`，题目图片为 `static/images/questions/`。数据库、图片、部分 JSON 配置被 Git 忽略，需单独部署和备份，不能只复制源码。

停止应用并备份数据库和图片后，对**已经具备主站基础表及历史字段的旧数据库**执行：

```powershell
# 添加 question_type / knowledge_modules；改名旧“选择题”；回填空题型
python migrate_db.py

# 要求 note_types 已存在：添加 visible_roles，空范围回填全部角色
python migrate_note_visibility.py

# 要求 visible_roles 已存在：将旧默认可见范围扩展为五角色
python migrate_add_roles.py
```

如只需题型改名、不重新识别：

```powershell
python migrate_db.py --rename-types-only
```

- 三个脚本均支持数据库路径参数，并在修改前生成 `.bak_时间戳`。
- 改名使用精确匹配且包含回收站；自动回填只处理非回收站题目。
- `migrate_db.py --force` 会覆盖能够重新判定的已有题型，无法判定时跳过；不要用它代替单纯改名。
- `migrate_add_roles.py` 只回填 NULL/空值/旧三角色默认值，保持其他自定义范围。
- NULL/空备注可见范围按“全部角色可见”处理；需要限制时请明确配置。

### 全新建库的现有限制

**`python addAdmin.py` 不是完整初始化流程。** 它只创建早期 `users`、`questions` 表及默认管理员，缺少备注表、软删除字段、年份/卷种/题号等当前运行所需结构。现有迁移也不能补齐全部缺口。

当前应使用与代码匹配的数据库备份及图片，或先补齐完整初始化/版本迁移方案。`data/schema.py` 用于检查、导出现有结构，不负责建库。历史默认管理员是 `admin / admin123`，使用后应立即改密。

| 主表 | 关键用途/运行字段 |
| --- | --- |
| `users` | 用户名、密码哈希、角色、`is_deleted`、创建/更新时间 |
| `questions` | 正文、答案、解析、来源、年份、卷种、题号、`question_type`、`knowledge_modules`、`isInRecycleBin` |
| `note_types` | 类型名、`visible_roles`、软删除和审计字段 |
| `question_notes` | 题目/类型/创建人关联、内容、软删除和审计字段 |
| `ai_whitelist` | AI 授权记录；首次检查时由代码按需建表 |

## DeepSeek 配置与启动

主站助手和标签推荐读取 `DEEPSEEK_API_KEY` 环境变量，或 Streamlit secrets 的 `deepseek_api_key`。

```powershell
$env:DEEPSEEK_API_KEY = "替换为自己的密钥"
python -m streamlit run main.py
```

也可创建本地 `.streamlit/secrets.toml`：

```toml
deepseek_api_key = "替换为自己的密钥"
```

默认地址 `http://localhost:8501`。没有密钥仍可使用非 AI 功能，助手会提示未配置。

当前主站助手不自动加载 `.env`，也不读取旧文档的 `OPENAI_API_KEY` / `OPENAI_API_BASE`。默认地址和模型分别定义在 `chains/deepseek_agent.py`、`tools/tag_suggest.py`，当前均为 `https://api.deepseek.com/v1`、`deepseek-flash`。这只是代码默认值，服务是否提供该模型需部署方核实；更换时调整相应调用或常量。

### 当前助手工作流

`main.py → pages/aiChatPage.py → chains/deepseek_agent.py`

1. 校验登录、AI 授权及密钥。管理员自动授权，其余角色需加入白名单。
2. 把系统提示、当前日期、历史问答和本轮问题发送给 DeepSeek。
3. 模型选择工具，服务器查询 SQLite，把结果交回模型。
4. 必要时继续调用工具，最多 8 轮模型请求；生成中文回答并引用题目 ID。

| 工具 | 功能与限制 |
| --- | --- |
| `search_questions` | 结构化检索，最多展示前 12 道；关键词不直接搜索备注 |
| `get_question` | 题目、答案、解析和元信息，解析按角色过滤；不附带备注 |
| `get_question_notes` | 读取角色范围内备注；目前每条只传前 200 个字符 |
| `search_notes` | 按备注关键词和可选类型查找关联题目；服务最多取 50 条，工具展示前 15 条摘要 |

当前助手**只读**，没有题目创建、修改、删除工具，也不使用 Chroma。单次 HTTP 请求超时 120 秒，不流式返回。“查看检索过程”仅显示工具结果前 1500 字符，不代表模型一定只收到这些字符；备注工具自身的 200 字符截断则确实影响模型可读内容。

AI 会把提问、历史对话、工具返回的题目/备注内容发送到配置的外部服务；标签推荐也会发送题目内容。会话隔离、删除过滤等已知问题见审计记录。

### 标签画像与批量回填

```powershell
# 用已有标注样本生成 data/knowledge_module_profile.json
python tools/build_tag_profile.py --sample 20

# 调用 AI 试标注，不写数据库，但仍发送请求并可能计费
python tools/tag_suggest.py --dry-run

# 回填空知识模块；先自行备份
python tools/tag_suggest.py
```

没有画像文件时使用内置画像。`--force` 会重新标注非回收站题目并覆盖成功返回的标签。画像生成和知识模块回填脚本不会自动备份业务库。

## 主站权限

权限定义为 `utils/permissions.py`；备注可见角色另行配置，管理员始终可见。

| 功能 | experiencer 体验用户 | viewer 普通用户 | advancer 高级用户 | editor 编辑员 | admin 管理员 |
| --- | --- | --- | --- | --- | --- |
| 检索题目与答案 | 是 | 是 | 是 | 是 | 是 |
| 查看题目解析 | 否 | 是 | 是 | 是 | 是 |
| 整卷导出 | 否 | 否 | 是 | 是 | 是 |
| 上传/更新、添加/软删备注 | 否 | 否 | 否 | 是 | 是 |
| 从更新页移入回收站 | 否 | 否 | 否 | 否 | 是 |
| 进入回收站并恢复 | 否 | 否 | 否 | 是 | 是 |
| 用户管理、卷种变更、备注类型管理入口 | 否 | 否 | 否 | 否 | 是 |
| 智能助手 | 白名单 | 白名单 | 白名单 | 白名单 | 自动授权 |

当前回收站“彻底删除”也对 editor 开放，与管理员删除权限设计不一致；编辑页紧凑备注组件也提供类型创建/修改操作，不能将“入口仅管理员”视为所有操作均已统一鉴权。本表不是安全保证。

## 审稿经验库

`review_exp_library/` 提供四类分类、草稿、提交、总编审核、发布/退回、归档、成员管理、增删对比和 ZIP 业务数据导入导出。

目前 `main.py` 菜单**没有挂接审稿库**。`pages/review.py` 可单独运行：

```powershell
python -m pip install SQLAlchemy
python -c "from pathlib import Path; Path('review_exp_library/data').mkdir(parents=True, exist_ok=True)"
python -m streamlit run pages/review.py --server.port 8502
```

- 默认数据库为 `review_exp_library/data/review_library.db`，可用 `REV_DB_PATH` 指定其他文件，父目录需存在。
- 独立用户表、`rev_*` 登录状态和 admin/chief/editor/viewer 权限，不与主站共享账号。
- 首次初始化创建默认 `admin / admin123` 和分类；总编需另行创建。`scripts/init_members.py` 的完成提示提到总编，但实际不会创建它。
- 图片为 `review_exp_library/static/images/review_cases/`，应与数据库共同备份。
- ZIP 导出是部分业务数据导出，不是完整灾备：缺少完整账号、分类、负责人关系和部分案例字段；导入新增记录且依赖目标库已有分类。详见审计记录。

## 旧版 RAG

历史路径 `pages/agentPage.py → chains/rag/agent.py → tools/*_tools.py` 不在当前主站调用链中。

依赖 LangChain、langchain-openai、langchain-classic、ChromaDB、sentence-transformers、python-dotenv，以及自行提供的 `chains/config.py`。该配置被 Git 忽略，当前检出不存在；工具参数 schema、用户实例缓存、权限及依赖兼容性仍需修复，不应直接当作可启用的主站功能。

`data/build_rag_db.py` 使用 `all-MiniLM-L6-v2` 写入 `data/rag_chroma_db/` 的 `question_bank` 集合，首次使用可能下载模型。构建与查询的嵌入方式、重复构建更新、删除同步和备注权限尚需核对。向量库文件存在不代表与 SQLite 实时一致。

## 代码导航

```text
main.py                         主站入口
pages/                          检索、助手、管理、导出、审稿入口
services/                       主站 SQLite 业务服务
tools/exam_type_utils.py         统一题型、知识模块、新教材规则
tools/tag_suggest.py             标签推荐与回填
tools/build_tag_profile.py       标签画像生成
tools/*_tools.py                 旧版 LangChain 工具
chains/deepseek_agent.py         当前 DeepSeek 工具调用助手
chains/rag/                     历史 RAG 助手
utils/                          权限、认证、富文本、图片、文档导出
data/schema.py                  现有数据库结构检查与导出
data/build_rag_db.py             历史向量库构建
review_exp_library/              审稿库 models_rev/services_rev/pages_rev/utils_rev
migrate_db.py                    题型/知识模块字段迁移及题型改名
migrate_note_visibility.py       备注可见角色字段迁移
migrate_add_roles.py             备注默认范围扩展为五角色
addAdmin.py                      历史最小初始化，非完整建库
.streamlit/config.toml          Streamlit 配置
docs/CODE_AUDIT.md               静态审计发现与验证范围
```

## 常见问题与维护

| 现象 | 检查方向 |
| --- | --- |
| `no such column: nt.visible_roles` | 对正确的旧业务库运行备注可见范围迁移，按需再运行角色迁移，重启应用 |
| `no such table` / 其他字段缺失 | 检查工作目录及数据库路径；空库或 `addAdmin.py` 生成的库不能直接运行当前主站 |
| expander 不支持 `on_change` / 缺少 `.open` | 确认应用启动环境，使用当前已验证的 Streamlit 版本 |
| 全选年份后展开空白、导航失效 | 使用含按需详情、分组局部执行和发送节流的版本，重启应用并刷新断开的浏览器会话 |
| 助手看不到长备注尾部 | 当前备注工具仅传 200 字符，仅改提示词无法解决 |
| 中文 PDF 导出失败 | 检查 fpdf2 和中文字体 |
| 审稿库初始化失败 | 检查 SQLAlchemy、数据库父目录存在且可写，主站与审稿库数据库不可混用 |

迁移、回填、彻底删除前备份数据库及图片；运行中的 SQLite 宜使用备份 API，或停服后复制。两个旧备注迁移脚本仍使用文件复制，应停服执行。当前图片去重后的共享引用未受完整保护，详见审计记录。

本次文档更新包含全仓语法检查和隔离复现，不代表全功能验收或生产安全认证。仓库未附许可证文件，本文不再将旧 README 的 MIT 声明视为已确认授权。
