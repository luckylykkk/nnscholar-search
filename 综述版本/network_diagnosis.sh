#!/bin/bash
# 网络诊断脚本，用于调试 Railway 部署中的网络问题

echo "=== 系统信息 ==="
uname -a
cat /etc/os-release

echo "=== DNS 配置 ==="
cat /etc/resolv.conf

echo "=== Hosts 文件 ==="
cat /etc/hosts

echo "=== 网络接口 ==="
ip addr

echo "=== 路由表 ==="
ip route

echo "=== PubMed API DNS 解析 ==="
dig eutils.ncbi.nlm.nih.gov

echo "=== DeepSeek API DNS 解析 ==="
dig api.siliconflow.cn

echo "=== PubMed API 连接测试 ==="
curl -v --max-time 10 https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=test

echo "=== DeepSeek API 连接测试 ==="
curl -v --max-time 10 https://api.siliconflow.cn/v1/chat/completions -d '{"model":"test"}' -H 'Content-Type: application/json'
