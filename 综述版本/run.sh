#!/bin/bash
# 启动脚本，用于 Railway 部署

# 设置 Python 路径
export PYTHONPATH=$PYTHONPATH:$(pwd)

# 启动应用
python wsgi.py
