# 学术文献智能检索系统

这是一个基于 Flask 的学术文献智能检索系统，支持多个学术文献数据源的集成搜索，包括 arXiv、PubMed 和 Semantic Scholar。系统提供了智能的文献检索和验证功能，帮助研究人员更高效地获取和筛选学术文献。

## 功能特点

- 多数据源集成搜索
- 智能检索策略生成
- 期刊指标信息展示（影响因子、JCR分区、CAS分区）
- 异步并发请求
- 文献导出功能
- 自动重试机制
- 速率限制保护
- 论文领域验证功能
- 多线程并行处理
- 实时进度显示
- 支持断点续传
- 详细视图/列表视图切换
- 批量导出选中文献

## 主要功能模块

### 1. 文献检索
- 支持输入多句研究文本
- 实时显示检索进度
- 支持多种筛选条件组合
- 提供详细的文献信息展示

### 2. 论文领域验证
- 支持CSV文件上传和选择
- 多线程并行验证处理
- 实时显示验证进度
- 支持验证过程中断和继续
- 自动分类并导出验证结果

### 3. 筛选功能
- 最低影响因子设置
- 每句话最大文献数限制
- 发表年份范围筛选
- JCR分区筛选
- 中科院分区筛选
- 学科领域筛选（可选）
- 最低引用数设置
- 数据源选择

## 技术栈

- Python 3.11+
- Flask (Web框架)
- aiohttp (异步HTTP客户端)
- ASGI (异步服务器网关接口)
- Bootstrap 5 (前端UI框架)

## 安装

1. 克隆仓库：
请直接下载这个分支，并解压

2. 创建并激活虚拟环境：
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 配置环境变量：
```bash
# 复制示例配置文件
cp .env.example .env
# 编辑 .env 文件，填入必要的 API 密钥
```

## 配置

在 `.env` 文件中配置以下环境变量：

- `DEEPSEEK_API_KEY`: DeepSeek API 密钥
- `SEMANTIC_SCHOLAR_API_KEY`: Semantic Scholar API 密钥
- `FLASK_ENV`: 运行环境 (development/production)
- `FLASK_DEBUG`: 调试模式 (1/0)

## 运行

```bash
python app.py
```

服务器将在 http://localhost:5000 启动。

## API 使用

### 搜索论文
```python
POST /api/search
Content-Type: application/json

{
    "query": "搜索关键词",
    "filters": {
        "papers_limit": 10,
        "min_if": 3.0,
        "year_range": [2020, 2024],
        "jcr_quartile": ["Q1", "Q2"],
        "cas_quartile": ["1", "2"],
        "sources": ["arxiv", "pubmed", "semanticscholar"]
    }
}
```

### 获取论文详情

```python
GET /api/paper/{paper_id}?source={source_name}
```

## 数据源支持

### arXiv
- 支持全文搜索
- 支持按年份过滤
- 支持获取 PDF 链接
- 支持分类搜索

### PubMed
- 支持标题和摘要搜索
- 支持按年份过滤
- 支持期刊信息查询

### Semantic Scholar
- 支持全文搜索
- 支持引用次数过滤
- 支持学科领域过滤
- 支持获取引用和参考文献

## 开发

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_arxiv_client.py -v

# 运行带有详细日志的测试
pytest tests/test_arxiv_client.py -v --log-cli-level=DEBUG
```

### 代码结构

```
.
├── app.py              # 主应用入口
├── requirements.txt    # 项目依赖
├── .env.example       # 环境变量示例
├── data/              # 数据文件
│   └── journal_metrics/  # 期刊指标数据
├── utils/             # 工具类
│   ├── __init__.py
│   ├── arxiv_client.py
│   ├── pubmed_client.py
│   ├── semantic_scholar_client.py
│   └── paper_source_interface.py
├── templates/         # HTML模板
│   └── index.html
└── tests/            # 测试文件
    ├── __init__.py
    └── test_arxiv_client.py
```

## 注意事项

1. API 速率限制  
为了减少API接口压力，请务必限制请求速率  
   - arXiv: 每秒1次请求
   - Semantic Scholar: 每秒5次请求
   - PubMed: 每秒3次请求

2. 错误处理
   - 所有 API 请求都有重试机制
   - 默认最多重试3次
   - 遇到速率限制时会自动等待

3. 数据导出
   - 支持导出为 CSV 格式
   - 自动下载相关 PDF 文件
   - 保存下载记录以支持断点续传



欢迎提交 Issue 和 Pull Request。

## 许可证

MIT License
