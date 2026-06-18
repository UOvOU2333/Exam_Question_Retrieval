# 📚 Exam Question Retrieval System

> 一个基于 **Streamlit** 构建的高中政治学科题库检索与智能分析系统。  
> 支持试题的 CRUD、语义检索（RAG）、笔记管理、多维度筛选与智能代理问答。

---

## ✨ 功能特性

### 🔍 试题检索
- **多维度筛选**：按卷种、年份、题号、关键词组合查询
- **基础/高级搜索**：支持在题目/答案/解析或来源中精确/模糊匹配
- **排序规则**：年份降序 → 卷种升序 → 题号升序

### 📄 试题管理
- **上传**：支持 Markdown 格式的题目内容、答案、解析，自动提取图片
- **更新**：编辑已有题目的任意字段
- **删除/恢复**：移入回收站，支持恢复与永久删除
- **复制模式**：方便批量维护试题

### 🏷️ 笔记系统
- 为题目添加分类标签和文字备注
- 按标签、内容、备注人检索
- 支持软删除与恢复

### 🤖 智能代理（AI Agent）
- 集成 **DeepSeek** 大语言模型 + LangChain
- **RAG 语义检索**：基于 `sentence-transformers` + ChromaDB 的向量检索
- **工具调用**：自动调用数据库查询、笔记检索、RAG 搜索等工具
- **智能分析**：支持题目讲解、相似题推荐、答案分析

### 👥 用户权限
| 角色 | 查看 | 新建/编辑 | 删除 | 永久删除/恢复 |
|:----|:---:|:--------:|:---:|:------------:|
| `viewer` | ✅ | ❌ | ❌ | ❌ |
| `editor` | ✅ | ✅ | ✅（软删除） | ❌ |
| `admin` | ✅ | ✅ | ✅ | ✅ |

---

## 🗂️ 项目结构

```
Exam_Question_Retrieval/
├── main.py                    # Streamlit 应用入口 & 路由
├── addAdmin.py                # 数据库初始化脚本（建表 + 创建默认 admin 用户）
│
├── pages/                     # Streamlit 页面
│   ├── searchPage.py          # 🔍 试题检索主页
│   ├── uploadPage.py          # 📤 试题上传
│   ├── updatePage.py          # ✏️ 试题编辑
│   ├── managingPage.py        # 🗑️ 回收站管理
│   ├── recycleBinPage.py      # ♻️ 回收站详细视图
│   ├── authPage.py            # 🔐 用户登录 / 个人主页
│   ├── userManagePage.py      # 👤 用户管理
│   ├── noteTypeManagingPage.py# 🏷️ 笔记标签管理
│   └── agentPage.py           # 🤖 智能代理页面
│
├── services/                  # 业务逻辑层
│   ├── question_services.py   # 题目 CRUD、搜索、回收站操作
│   ├── note_services.py       # 笔记 & 笔记标签 CRUD
│   ├── user_services.py       # 用户认证 & 管理
│   └── recycleBin_services.py # 回收站相关操作（含图片清理）
│
├── tools/                     # LangChain 工具（Agent 调用）
│   ├── question_tools.py      # 题目查询/创建/更新/删除工具
│   ├── note_tools.py          # 笔记 & 标签相关工具
│   └── rag_tool.py            # RAG 语义检索工具
│
├── chains/                    # AI Agent 链
│   ├── rag/
│   │   ├── agent.py           # Agent 构建（DeepSeek + LangChain）
│   │   └── prompt.py          # 系统提示词（行为准则、工具说明）
│   └── loger.py               # Agent 日志记录
│
├── utils/                     # 工具函数
│   ├── auth_utils.py          # 登录校验 & 角色检查
│   ├── file_utils.py          # 文件/图片处理
│   ├── navbar_utils.py        # 侧边栏导航
│   ├── note_utils.py          # 笔记相关 UI 组件
│   ├── render_utils.py        # Markdown/图片渲染
│   └── multi_func.py          # 多选/通用组件
│
├── data/                      # 数据层
│   ├── questions.db           # SQLite 数据库（题目、用户、笔记）
│   ├── build_rag_db.py        # 从 SQLite 构建 Chroma 向量库
│   ├── schema.py              # 数据库结构导出分析脚本
│   └── rag_chroma_db/         # ChromaDB 向量存储目录
│
├── static/images/             # 上传的图片资源
│   ├── logo/                  # 系统 Logo
│   └── questions/             # 题目配图
│
└── .streamlit/config.toml     # Streamlit 配置文件
```

---

## ⚙️ 快速开始

### 前置依赖

- Python 3.10+
- [Streamlit](https://streamlit.io/)
- SQLite3（内置）
- ChromaDB（向量库）
- sentence-transformers（语义嵌入模型）

### 安装

```bash
# 克隆项目
git clone https://github.com/your-repo/Exam_Question_Retrieval.git
cd Exam_Question_Retrieval

# 安装依赖
pip install -r requirements.txt
```

主要依赖包括：

```
streamlit
streamlit-antd-components
langchain
langchain-openai
langchain-classic
chromadb
sentence-transformers
Pillow
python-dotenv
```

### 配置

创建 `.env` 文件配置 DeepSeek API：

```env
OPENAI_API_KEY=your_deepseek_api_key
OPENAI_API_BASE=https://api.deepseek.com
```

### 初始化数据库

```bash
python addAdmin.py
```

默认创建管理员账户：
- 用户名：`admin`
- 密码：`admin123`

### 构建 RAG 向量库（可选）

```bash
python data/build_rag_db.py
```

### 启动

```bash
streamlit run main.py
```

默认访问地址：`http://localhost:8501`

---

## 🗄️ 数据库设计

系统使用 **SQLite** 作为主数据库，**ChromaDB** 作为向量检索库。

### 主要数据表

| 表名 | 说明 |
|:----|:-----|
| `users` | 用户信息（用户名、密码哈希、角色、创建时间） |
| `questions` | 试题（内容、答案、解析、来源、年份、卷种、题号、回收站标记） |
| `note_types` | 笔记标签类型（名称、创建人、删除标记） |
| `question_notes` | 题目笔记（关联题目、标签类型、笔记内容、创建人） |

### RAG 向量库

使用 `all-MiniLM-L6-v2` 模型将题目内容嵌入为向量，存入 ChromaDB，支持语义层面的模糊检索。

---

## 🧠 智能代理工作流程

```
用户提问
    │
    ▼
LLM (DeepSeek) 解析意图
    │
    ├── 结构化查询 → search_questions_tool() → SQLite 精确匹配
    │
    ├── 语义搜索 → rag_search_tool() → ChromaDB 向量检索
    │
    ├── 题目详情 → get_question_tool() → 获取完整题目
    │
    ├── 笔记查询 → get_question_notes_tool() → 获取评论
    │
    └── 创建/更新 → 对应工具 → 写回数据库
    │
    ▼
    综合回答（标注信息来源）
```

---

## 🔐 权限体系

| 功能 | viewer | editor | admin |
|:----|:-----:|:------:|:-----:|
| 检索试题 | ✅ | ✅ | ✅ |
| RAG 语义搜索 | ✅ | ✅ | ✅ |
| 查看笔记 | ✅ | ✅ | ✅ |
| 添加笔记 | ❌ | ✅ | ✅ |
| 上传/编辑题目 | ❌ | ✅ | ✅ |
| 删除题目（回收站） | ❌ | ✅ | ✅ |
| 永久删除/恢复 | ❌ | ❌ | ✅ |
| 管理用户 | ❌ | ❌ | ✅ |

---

## 🛠️ 技术栈

| 技术 | 用途 |
|:----|:-----|
| **[Streamlit](https://streamlit.io/)** | 前端 UI 框架 |
| **Streamlit Antd Components** | UI 组件库（菜单、表格等） |
| **[LangChain](https://www.langchain.com/)** | AI Agent 框架 |
| **[DeepSeek](https://deepseek.com/)** | 大语言模型（Agent 推理） |
| **[ChromaDB](https://www.trychroma.com/)** | 向量数据库 |
| **[sentence-transformers](https://www.sbert.net/)** | 语义嵌入模型 |
| **SQLite** | 关系型数据库 |

---

## 📄 License

MIT License

---

*本项目为高中政治学科题库管理系统，使用 Streamlit + LangChain + RAG 技术栈构建。*
