# NNScholar - 医学文献智能检索与分析系统

NNScholar是一个基于Python的医学文献智能检索与分析系统，它能够帮助研究者快速检索、分析和整理医学文献。

## 功能特点

- 智能文献检索
  - 使用PubMed API进行文献检索
  - 支持智能检索策略生成
  - 支持检索策略的手动修改和优化
  - 实时显示搜索进度和详细日志
  
- 文献分析
  - 自动分析文献的年份分布
  - 智能计算文献相关性得分
  - 支持多维度筛选（年份、影响因子、JCR分区、CAS分区）
  
- 热点分析
  - 期刊热点主题分析
  - 研究热点趋势可视化
  - 热点作者统计分析
  - 生成热力图展示研究热度
  
- 数据导出
  - 支持Excel格式导出（包含详细的文献信息）
  - 支持Word文档导出（包含格式化的文献报告）
  - 自动导出初始检索结果和筛选后结果
  
- 期刊指标
  - 自动获取期刊的影响因子
  - 显示JCR分区信息
  - 显示中科院分区信息

## 安装说明

1. 安装Python 3.8或更高版本
2. 克隆或下载本项目
3. 安装依赖包：
```bash
pip install -r requirements.txt
```

## 配置说明

1. 在项目根目录创建`.env`文件，添加以下配置：
```
DEEPSEEK_API_KEY=your_deepseek_api_key
PUBMED_API_KEY=your_pubmed_api_key
PUBMED_EMAIL=your_email
TOOL_NAME=nnscholar_pubmed
PUBMED_API_URL=https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
```

2. 替换以下配置项：
- `DEEPSEEK_API_KEY`：你的DeepSeek API密钥（用于生成智能检索策略）
- `PUBMED_API_KEY`：你的PubMed API密钥（用于文献检索）
- `PUBMED_EMAIL`：你的邮箱地址（PubMed API要求）

## 使用说明

1. 启动应用：
```bash
python app.py
```

2. 访问应用：
- 打开浏览器访问 `http://localhost:5000`

3. 文献检索流程：
   - 输入检索关键词
   - 系统自动生成优化的检索策略
   - 可以根据需要修改检索策略
   - 执行检索获取文献列表
   - 实时查看搜索进度和详细日志
   - 使用筛选条件过滤文献
   - 导出所需的文献信息

4. 热点分析功能：
   - 选择目标期刊和时间范围
   - 可选择特定研究方向关键词
   - 系统自动分析热点主题和趋势
   - 生成热力图和趋势图
   - 展示高产作者和研究团队

5. 导出功能：
   - Excel导出：包含文献的详细信息，适合数据分析
   - Word导出：生成格式化的文献报告，适合阅读和分享
   - 系统会同时保存初始检索结果和筛选后的结果

## 文件结构

```
nnscholar-search-main/
├── app.py              # 主应用程序
├── analyze_papers.py   # 文献分析脚本
├── journal_analyzer.py # 期刊分析工具
├── requirements.txt    # 依赖包列表
├── .env               # 环境配置文件
├── data/              # 数据文件目录
│   └── journal_metrics/  # 期刊指标数据
├── exports/           # 导出文件目录
├── logs/              # 日志文件目录
├── static/            # 静态资源目录
│   └── images/        # 热力图等图像文件
└── templates/         # 模板文件目录
```

## 注意事项

1. 首次运行时会自动下载NLTK数据
2. 确保有稳定的网络连接
3. API密钥请妥善保管，不要泄露
4. 导出文件会自动保存在exports目录下
5. 日志文件会自动保存在logs目录下
6. 热力图等分析图表保存在static/images目录

## 常见问题

1. 如果遇到NLTK数据下载问题，可以手动下载并放置在正确的目录
2. 如果遇到API限制，请检查API密钥是否正确
3. 如果需要更改端口，可以在app.py中修改
4. 如果导出文件失败，请检查exports目录的权限
5. 如果热点分析图表不显示，检查static目录权限

## 更新日志

### 2024.02
- 添加了实时搜索进度显示功能
- 添加了详细的搜索日志记录
- 添加了Word文档导出功能
- 优化了文献相关性计算
- 改进了检索策略生成
- 添加了更详细的筛选统计信息
- 新增期刊热点分析功能
- 添加热点主题可视化展示

## 许可证

MIT License

## 贡献指南

欢迎提交Issue和Pull Request来帮助改进项目。

## 快速开始

### 本地运行

1. 克隆仓库
```bash
git clone https://github.com/yourusername/nnscholar-search.git
cd nnscholar-search
```

2. 安装依赖
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的API密钥
```

4. 运行应用
```bash
flask run
```

### Railway部署

1. Fork 这个仓库到你的GitHub账号

2. 在Railway.app注册账号并连接你的GitHub

3. 创建新项目，选择从GitHub导入

4. 选择fork的仓库

5. Railway会自动检测配置并部署

6. 在Railway的Variables面板中添加环境变量：
   - DEEPSEEK_API_KEY
   - PUBMED_API_KEY
   - PUBMED_EMAIL
   
7. 等待部署完成，访问生成的域名即可使用

## 环境变量说明

| 变量名 | 说明 | 示例值 |
|--------|------|--------|
| DEEPSEEK_API_KEY | DeepSeek API密钥 | sk-xxx... |
| PUBMED_API_KEY | PubMed API密钥 | fc304... |
| PUBMED_EMAIL | PubMed访问邮箱 | your@email.com |

## 技术栈

- Python 3.9
- Flask
- ThreadPoolExecutor
- PubMed API
- DeepSeek AI

## 更新日志

### v3.0
- 支持50并发用户
- 添加前端进度显示
- 优化搜索性能

### v2.159
- 更新核心功能
- 优化页面布局

### v1.1
- 添加多用户并发系统

### v1.0
- 首次发布
## todo：  

- 修复前端显示，在常规模式和热点分析模式之间切换，如果常规模式已经有结果，不会隐藏相关的容器。  
- 热点分析模式下，应该使用关键词而不是严格分词  
- 热点分析模式下，会话隔离测试  
