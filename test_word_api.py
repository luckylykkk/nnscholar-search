#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试Word导出API
"""

import requests
import json

def setup_test_data():
    """设置测试数据"""
    try:
        # 先进行一次搜索来创建缓存数据
        search_url = "http://localhost:5000/api/search"
        search_data = {
            "query": "cancer treatment",
            "mode": "single",
            "filters": {
                "year_start": 2020,
                "year_end": 2024,
                "min_if": 0,
                "jcr_quartile": [],
                "cas_quartile": [],
                "papers_limit": 10
            }
        }

        headers = {
            "Content-Type": "application/json",
            "sid": "test_session_123"
        }

        print("🔍 先进行搜索以创建测试数据...")
        response = requests.post(search_url, json=search_data, headers=headers)

        if response.status_code == 200:
            print("✅ 搜索成功，测试数据已创建")
            return True
        else:
            print(f"❌ 搜索失败: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ 设置测试数据失败: {e}")
        return False

def test_word_export_api():
    """测试Word导出API"""
    try:
        # 先设置测试数据
        if not setup_test_data():
            print("❌ 无法设置测试数据，跳过API测试")
            return

        # API端点
        url = "http://localhost:5000/api/export/word"

        # 请求数据
        data = {
            "query": "cancer treatment",
            "format": "word"
        }

        # 请求头
        headers = {
            "Content-Type": "application/json",
            "sid": "test_session_123"  # 测试会话ID
        }
        
        print("🧪 开始测试Word导出API...")
        print(f"📡 请求URL: {url}")
        print(f"📦 请求数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
        
        # 发送请求
        response = requests.post(url, json=data, headers=headers)
        
        print(f"📊 响应状态码: {response.status_code}")
        print(f"📋 响应头: {dict(response.headers)}")
        
        if response.status_code == 200:
            # 检查是否是文件响应
            content_type = response.headers.get('content-type', '')
            if 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' in content_type:
                print("✅ 收到Word文件响应")
                print(f"📄 文件大小: {len(response.content)} 字节")
                
                # 保存文件进行验证
                filename = "test_api_export.docx"
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"💾 文件已保存为: {filename}")
                
            else:
                print(f"⚠️ 意外的内容类型: {content_type}")
                print(f"📝 响应内容: {response.text[:500]}")
        else:
            print(f"❌ API请求失败")
            try:
                error_data = response.json()
                print(f"🔍 错误信息: {json.dumps(error_data, ensure_ascii=False, indent=2)}")
            except:
                print(f"📝 响应文本: {response.text}")
                
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_word_export_api()
