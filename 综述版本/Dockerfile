FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖和网络诊断工具
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    dnsutils \
    curl \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 下载 NLTK 数据
RUN python -m nltk.downloader punkt stopwords wordnet

# 复制应用代码
COPY . .

# 创建启动脚本
RUN echo '#!/bin/bash\n\
# 添加 PubMed API 域名到 hosts 文件\n\
echo "130.14.29.110 eutils.ncbi.nlm.nih.gov" >> /etc/hosts\n\
\n\
# 设置多个 DNS 服务器\n\
echo "nameserver 8.8.8.8\nnameserver 8.8.4.4\nnameserver 1.1.1.1" > /etc/resolv.conf\n\
\n\
# 打印网络诊断信息\n\
echo "=== 网络诊断信息 ==="\n\
echo "PubMed DNS 解析:"\n\
dig eutils.ncbi.nlm.nih.gov\n\
\n\
echo "PubMed 连接测试:"\n\
curl -v --max-time 10 https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=test 2>&1 | grep -E "Connected to|SSL connection|HTTP/"\n\
\n\
# 启动应用\n\
python wsgi.py\n\
' > /app/start.sh

RUN chmod +x /app/start.sh

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PORT=5000
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV PYTHONDONTWRITEBYTECODE=1

# 暴露端口
EXPOSE 5000

# 使用启动脚本
CMD ["/app/start.sh"]
