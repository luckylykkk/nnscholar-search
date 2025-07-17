# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NNScholar（智能学术文献检索与分析平台）是一个基于AI驱动的Flask Web应用，专为科研工作者设计。该项目集成了DeepSeek AI技术，提供智能化的文献检索、深度分析和学术写作支持。

## Architecture

### Core Components
- **Flask Web Application** (`app.py`) - 主应用程序，包含路由、WebSocket处理和核心业务逻辑
- **Journal Analyzer** (`journal_analyzer.py`) - 期刊分析模块，处理期刊热点分析和数据可视化
- **Paper Analyzer** (`analyze_papers.py`) - 论文分析模块，处理文献关键词提取和分析
- **Templates** - Flask模板文件：
  - `templates/index.html` - 专业检索界面
  - `templates/chat.html` - 智能聊天界面
  - `templates/admin.html` - 管理界面
  - `templates/pubmed_expert_prompt.md` - PubMed专家提示模板

### Key Features
- **双界面设计**: 专业检索界面(`/`)和智能聊天界面(`/chat`)
- **AI智能推荐系统**: 基于影响因子和创新性的文献推荐
- **实时WebSocket通信**: 用于实时搜索进度和结果更新
- **多格式数据导出**: 支持Excel和Word格式的文献报告导出
- **期刊热点分析**: 可视化分析期刊研究趋势和热点主题

## Development Commands

### Environment Setup
```bash
# 创建虚拟环境 (if using virtualenv)
python -m venv nnscholarweb
source nnscholarweb/bin/activate  # Linux/Mac
# 或
nnscholarweb\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### Running the Application
```bash
# 开发模式启动
python app.py

# 生产模式启动 (使用gunicorn)
gunicorn --worker-class eventlet -w 1 app:app
```

### API Configuration
项目需要以下环境变量配置：
- `DEEPSEEK_API_KEY` - DeepSeek AI API密钥
- `EMBEDDING_API_KEY` - 嵌入模型API密钥
- 其他API配置请参考`.env`文件模板

## Code Structure

### Main Application Flow
1. **用户界面**: 两个主要界面提供不同的交互方式
2. **文献检索**: 通过PubMed API进行学术文献搜索
3. **AI分析**: 使用DeepSeek AI进行文献内容分析和推荐
4. **数据处理**: 包含影响因子、JCR分区、中科院分区等期刊质量指标
5. **结果展示**: 多维度展示检索结果，包括相关性评分和筛选功能

### Key Modules
- **WebSocket通信**: 实时进度更新和结果推送
- **会话管理**: 用户检索历史和会话状态管理
- **数据导出**: 格式化的Excel和Word文档生成
- **可视化**: 使用matplotlib和seaborn进行数据可视化

## Dependencies

### Core Dependencies
- **Flask 3.0.2** - Web框架
- **Flask-SocketIO 5.3.6** - WebSocket支持
- **requests 2.31.0** - HTTP请求处理
- **gunicorn 21.2.0** - WSGI服务器

### AI & NLP
- **langchain-community 0.0.19** - AI应用框架
- **nltk 3.8.1** - 自然语言处理
- **scikit-learn 1.4.0** - 机器学习

### Data Processing
- **pandas 2.2.0** - 数据处理
- **numpy 1.26.4** - 数值计算
- **matplotlib 3.8.2** - 数据可视化
- **seaborn 0.13.2** - 统计可视化

### Document Processing
- **python-docx 1.1.0** - Word文档生成
- **openpyxl 3.1.2** - Excel文档处理
- **beautifulsoup4 4.12.3** - HTML解析

## Important Notes

### Testing
项目目前没有配置标准测试框架。建议通过以下方式进行测试：
- 启动应用后访问 `/` 和 `/chat` 界面进行功能测试
- 使用提供的测试数据进行文献检索功能验证

### Deployment
项目配置了多种部署选项：
- **Railway**: 使用 `railway.toml` 配置
- **Heroku**: 使用 `Procfile` 配置
- **Docker**: 支持容器化部署
- **Nginx**: 提供了nginx配置文件

### Session Management
应用使用Flask Session进行会话管理，包括：
- 用户检索历史存储
- 会话状态维护
- 临时数据缓存

### File Structure
- `static/` - 静态资源文件
- `templates/` - Flask模板文件
- `data/` - 数据文件（期刊指标等）
- `logs/` - 日志文件
- `exports/` - 导出文件临时存储