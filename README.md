# NNScholar - 医学文献智能检索与分析系统

🔬 **NNScholar** 是一个基于AI的医学文献智能检索与分析系统，采用现代化聊天界面设计，为研究者提供从文献检索到学术写作的全流程支持。

## ✨ 核心功能

### 🔍 智能文献检索
- **AI驱动的检索策略生成**：基于DeepSeek AI自动生成优化的PubMed检索策略
- **双模式检索**：支持单句模式和段落模式检索
- **实时进度追踪**：详细的搜索进度显示和日志记录
- **智能相关性评分**：基于嵌入模型计算文献相关度
- **多维度筛选**：年份、影响因子、JCR分区、中科院分区等筛选条件

### 🤖 AI智能推荐系统
- **⭐ 代表性文章推荐**：基于影响因子、创新性和学术质量智能筛选最具价值的文献
- **🎯 智能推荐模块**：NNScholar科研助手为您推荐最重要的研究内容
- **🔍 精确查找文献**：从已检索文献中严格筛选符合特定要求的文献，支持充分性评分
- **📊 符合条件充分性评估**：按照90-100%（高度符合）、70-89%（中度符合）、50-69%（基本符合）进行评分排序

### 📊 学术分析功能
- **📈 全面研究现状分析**：基于检索文献生成详细的研究现状报告
- **📝 综述选题建议**：智能分析文献热点，提供综述写作选题
- **🔬 论著选题建议**：识别研究空白，提供原创研究方向
- **📚 完整综述生成**：自动生成结构化的文献综述文档
- **🚀 前沿研究方向**：发现最新研究趋势和热点
- **🧩 研究空白与机会**：识别未被充分研究的领域

### 🎯 期刊热点分析
- **热点主题识别**：分析期刊研究热点和趋势
- **可视化展示**：热力图、词云图、趋势图多维度展示
- **热点作者统计**：识别领域内高产作者和研究团队
- **时间序列分析**：追踪研究热点的时间变化

### 🛠️ 深度分析工具箱
- **AI投稿选刊**：基于研究内容智能推荐合适期刊
- **论文翻译**：专业的学术论文中英文翻译
- **论文润色**：学术写作语言优化
- **AI选题**：基于文献分析的研究选题建议
- **研究方法分析**：实验设计与统计分析指导
- **文献综述大纲**：综述结构分析与大纲生成
- **文献筛选**：精准筛选特定方向文献
- **创新点识别**：发现研究空白与创新方向
- **基金申请书撰写**：基于专业提示的基金申请指导

### 📄 数据导出
- **Excel表格导出**：包含影响因子、JCR分区、中科院分区的详细文献信息
- **Word文档导出**：格式化的文献报告，包含完整期刊质量信息
- **多格式支持**：支持初始检索和筛选后结果的分别导出

### 💬 现代化界面
- **DeepSeek风格聊天界面**：直观的对话式交互体验
- **历史会话管理**：保存和管理检索历史
- **响应式设计**：支持桌面和移动设备
- **实时状态反馈**：搜索进度、处理状态实时显示

## 🚀 快速开始

### 环境要求
- Python 3.8+
- 稳定的网络连接
- DeepSeek API密钥
- PubMed API密钥（可选，用于提高检索速度）

### 本地部署

1. **克隆项目**
```bash
git clone https://github.com/luckylykkk/NNscholarweb.git
cd NNscholarweb
```

2. **安装依赖**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **配置环境变量**
在项目根目录创建`.env`文件：
```env
DEEPSEEK_API_KEY=your_deepseek_api_key
PUBMED_API_KEY=your_pubmed_api_key  # 可选
PUBMED_EMAIL=your_email@example.com
TOOL_NAME=nnscholar_pubmed
PUBMED_API_URL=https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
```

4. **启动应用**
```bash
python app.py
```

5. **访问应用**
打开浏览器访问：
- 聊天界面：`http://localhost:5000/chat`
- 传统界面：`http://localhost:5000`

## 📖 使用指南

### 🔍 文献检索流程

1. **输入检索内容**
   - 在聊天界面输入研究主题或关键词
   - 支持中英文混合输入
   - 可以输入完整的研究问题

2. **AI智能检索**
   - 系统自动生成优化的PubMed检索策略
   - 实时显示检索进度和详细日志
   - 智能计算文献相关性评分

3. **结果筛选与分析**
   - 使用多维度筛选条件过滤文献
   - 查看文献的影响因子和分区信息
   - 获得精准的文献列表

4. **深度分析**
   - 📊 **全面研究现状分析**：生成详细的研究现状报告
   - 📝 **综述选题**：获取基于真实文献的综述选题建议
   - 🔬 **论著选题**：发现研究空白，获得原创研究方向
   - 📚 **生成完整综述**：自动生成结构化综述文档

5. **数据导出**
   - 📊 **Excel表格**：包含影响因子、分区信息的详细数据
   - 📄 **Word文档**：格式化的文献报告

### 🎯 期刊热点分析

1. **选择分析模式**
   - 切换到"热点分析"模式
   - 输入目标期刊名称

2. **设置分析参数**
   - 选择时间范围（起始年份-结束年份）
   - 可选择特定研究方向关键词

3. **获取分析结果**
   - 热点主题热力图
   - 关键词词云图
   - 研究趋势时间序列
   - 热点作者排名

### 🔍 精确查找文献

在完整文献列表下方，点击"🔍 精确查找文献"按钮：
1. **输入精确要求**：例如"和降糖药物相关研究"
2. **严格筛选标准**：系统会严格排除不符合要求的文献（如他汀类药物研究）
3. **充分性评分**：按照符合条件的充分性（90-100%、70-89%、50-69%）进行排序
4. **详细筛选理由**：每篇文献都有详细的符合筛选条件的理由说明

### 🛠️ 深度分析工具

访问聊天界面右上角的"🔬 深度分析"按钮，可使用：
- AI投稿选刊、论文翻译、论文润色
- AI选题、研究方法分析、文献综述大纲
- 文献筛选、创新点识别、基金申请书撰写
- 等覆盖学术研究全流程的工具

## 📁 项目结构

```
NNscholarweb/
├── app.py                 # 主应用程序
├── analyze_papers.py      # 文献分析脚本
├── journal_analyzer.py    # 期刊分析工具
├── requirements.txt       # 依赖包列表
├── .env                  # 环境配置文件
├── data/                 # 数据文件目录
│   └── journal_metrics/  # 期刊指标数据
├── exports/              # 导出文件目录
├── logs/                 # 日志文件目录
├── static/               # 静态资源目录
│   ├── images/           # 热力图等图像文件
│   └── js/               # JavaScript文件
├── templates/            # 模板文件目录
│   ├── index.html        # 传统界面
│   ├── chat.html         # 聊天界面
│   └── admin.html        # 管理界面
└── 原来版本/              # 原始版本备份
```

## 🔧 技术架构

### 后端技术栈
- **Python 3.8+** - 主要开发语言
- **Flask** - Web框架
- **Flask-SocketIO** - 实时通信
- **ThreadPoolExecutor** - 并发处理
- **pandas** - 数据处理
- **python-docx** - Word文档生成
- **openpyxl** - Excel文档生成
- **scikit-learn** - 机器学习（相关性计算）
- **nltk** - 自然语言处理

### 前端技术栈
- **HTML5/CSS3** - 页面结构和样式
- **JavaScript (ES6+)** - 交互逻辑
- **Bootstrap 5** - UI框架
- **ECharts** - 数据可视化
- **Socket.IO** - 实时通信

### 外部API
- **DeepSeek AI** - 智能检索策略生成和文献分析
- **嵌入模型API** - 文献相关度计算和语义匹配（支持SiliconFlow等）
- **PubMed API** - 医学文献检索
- **期刊指标数据库** - 影响因子和分区信息

## ⚙️ 配置说明

### 环境变量

| 变量名 | 说明 | 必需 | 示例值 |
|--------|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek AI API密钥 | ✅ | `sk-xxx...` |
| `EMBEDDING_API_KEY` | 嵌入模型API密钥 | ✅ | `sk-xxx...` |
| `EMBEDDING_API_URL` | 嵌入模型API地址 | ❌ | `https://api.siliconflow.cn/v1/embeddings` |
| `EMBEDDING_MODEL` | 嵌入模型名称 | ❌ | `BAAI/bge-m3` |
| `PUBMED_API_KEY` | PubMed API密钥 | ⚠️ | `fc304...` |
| `PUBMED_EMAIL` | PubMed访问邮箱 | ⚠️ | `your@email.com` |
| `TOOL_NAME` | 工具标识 | ❌ | `nnscholar_pubmed` |
| `PUBMED_API_URL` | PubMed API地址 | ❌ | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` |

> ⚠️ PubMed API密钥可选，但建议配置以提高检索速度和稳定性
> ✅ 嵌入模型API密钥必需，用于文献相关度计算和精确查找功能

### 筛选设置
用户可以在聊天界面右下角的设置面板中自定义：
- 发表年份范围
- 最低影响因子
- JCR分区（Q1-Q4）
- 中科院分区（1-4区）
- 文献类型筛选
- 显示数量限制

## 🚨 注意事项

1. **首次运行**：会自动下载NLTK数据包，请确保网络连接稳定
2. **API密钥安全**：请妥善保管API密钥，不要在代码中硬编码或泄露
3. **文件权限**：确保`exports/`、`logs/`、`static/images/`目录有写入权限
4. **网络连接**：需要稳定的网络连接访问PubMed和DeepSeek API
5. **浏览器兼容性**：推荐使用Chrome、Firefox、Edge等现代浏览器

## ❓ 常见问题

### 安装和配置问题
- **NLTK数据下载失败**：手动下载并放置在正确目录，或使用代理
- **依赖包安装失败**：使用`pip install --upgrade pip`更新pip后重试
- **端口占用**：修改`app.py`中的端口号或关闭占用端口的程序

### 功能使用问题
- **检索无结果**：检查网络连接和API密钥配置
- **分析功能无响应**：确保先进行文献检索，再使用分析功能
- **导出文件失败**：检查`exports/`目录权限和磁盘空间
- **图表不显示**：检查`static/images/`目录权限和浏览器JavaScript设置

### API相关问题
- **DeepSeek API限制**：检查API密钥余额和调用频率限制
- **PubMed API超时**：网络不稳定时可能出现，重试即可
- **检索策略生成失败**：检查DeepSeek API密钥是否正确配置

## 🔄 更新日志

### v2.1.0 (2025-06-27) - AI智能推荐系统
- ⭐ **代表性文章推荐**：基于影响因子、创新性和学术质量智能筛选最具价值的文献
- 🎯 **智能推荐模块**：NNScholar科研助手为您推荐最重要的研究内容
- 🔍 **精确查找文献**：从已检索文献中严格筛选符合特定要求的文献
- 📊 **充分性评分系统**：按照90-100%（高度符合）、70-89%（中度符合）、50-69%（基本符合）进行评分排序
- 🧠 **严格筛选标准**：宁可少选也不能错选，确保返回文献严格满足用户要求
- 🎨 **优化界面布局**：检索结果摘要 → AI推荐模块 → 完整文献列表的三层布局设计
- 🔧 **嵌入模型集成**：完全基于嵌入模型的相关度计算，提高语义匹配准确性

### v2.0.0 (2025-06-27) - 重大更新
- ✨ **全新DeepSeek风格聊天界面**：现代化的对话式交互体验
- 🤖 **AI驱动的文献分析**：集成DeepSeek AI进行智能分析
- 📊 **四大核心分析功能**：
  - 全面研究现状分析
  - 综述选题建议
  - 论著选题建议
  - 完整综述生成
- 🛠️ **深度分析工具箱**：覆盖学术研究全流程的9大工具
- 📄 **增强导出功能**：Word和Excel导出包含影响因子和分区信息
- 💬 **历史会话管理**：保存和管理检索历史
- ⚙️ **可自定义筛选设置**：用户可自定义文献筛选条件
- 🔧 **技术架构优化**：改进会话管理和缓存机制

### v1.x (2024)
- 🔍 基础文献检索功能
- 📈 期刊热点分析和可视化
- 📊 数据导出（Excel/Word）
- 🎯 实时搜索进度显示
- 📋 详细搜索日志记录
- 🔬 文献相关性计算优化

## 🚀 部署指南

### 本地部署
参考上方"快速开始"部分

### 云平台部署

#### Railway部署
1. Fork本项目到您的GitHub账号
2. 在[Railway.app](https://railway.app)注册并连接GitHub
3. 创建新项目，选择从GitHub导入
4. 在Variables面板添加环境变量
5. 等待自动部署完成

#### 其他平台
- **Heroku**: 支持一键部署
- **Vercel**: 适合静态部署
- **Docker**: 提供Dockerfile支持

## 🤝 贡献指南

我们欢迎所有形式的贡献！

### 如何贡献
1. 🍴 Fork 本项目
2. 🌿 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 💾 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 📤 推送到分支 (`git push origin feature/AmazingFeature`)
5. 🔄 开启 Pull Request

### 贡献类型
- 🐛 Bug修复
- ✨ 新功能开发
- 📚 文档改进
- 🎨 UI/UX优化
- 🔧 性能优化
- 🧪 测试用例

## 📞 支持与反馈

- **GitHub Issues**: [提交问题](https://github.com/luckylykkk/NNscholarweb/issues)
- **功能建议**: 欢迎在Issues中提出新功能建议
- **使用交流**: 可以在Issues中分享使用经验和最佳实践

## 📋 开发计划

### 近期计划
- [ ] 移动端适配优化
- [ ] 多语言支持（英文界面）
- [ ] 文献引用格式导出
- [ ] 批量文献下载功能
- [ ] 精确查找功能的进一步优化
- [ ] 更多嵌入模型支持

### 长期规划
- [ ] 机器学习模型优化
- [ ] 更多数据库支持（Web of Science、Scopus等）
- [ ] 协作功能（团队共享、评论等）
- [ ] API接口开放
- [ ] 智能推荐算法持续优化

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源协议。

## 🙏 致谢

感谢以下项目和服务的支持：

- [PubMed](https://pubmed.ncbi.nlm.nih.gov/) - 提供医学文献数据
- [DeepSeek](https://www.deepseek.com/) - 提供AI分析能力
- [Flask](https://flask.palletsprojects.com/) - Web框架支持
- [Bootstrap](https://getbootstrap.com/) - UI组件库
- [ECharts](https://echarts.apache.org/) - 数据可视化
- [Socket.IO](https://socket.io/) - 实时通信

---

<div align="center">

**⭐ 如果这个项目对您有帮助，请给我们一个Star！**

[![GitHub stars](https://img.shields.io/github/stars/luckylykkk/NNscholarweb.svg?style=social&label=Star)](https://github.com/luckylykkk/NNscholarweb)
[![GitHub forks](https://img.shields.io/github/forks/luckylykkk/NNscholarweb.svg?style=social&label=Fork)](https://github.com/luckylykkk/NNscholarweb/fork)

Made with ❤️ by [luckylykkk](https://github.com/luckylykkk)

</div>
