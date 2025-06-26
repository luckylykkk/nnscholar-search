#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试分析功能API
"""

import requests
import json
import time

def test_api_endpoint(url, data, description):
    """测试单个API端点"""
    print(f"\n🧪 测试 {description}")
    print(f"📡 请求URL: {url}")
    
    headers = {
        "Content-Type": "application/json",
        "sid": "test_session_123"
    }
    
    try:
        print("📤 发送请求...")
        response = requests.post(url, json=data, headers=headers, timeout=30)
        
        print(f"📊 响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                if result.get('success'):
                    print("✅ API调用成功")
                    print(f"📝 响应长度: {len(result.get('analysis', result.get('suggestions', result.get('review', ''))))} 字符")
                else:
                    print(f"❌ API返回错误: {result.get('error', '未知错误')}")
            except json.JSONDecodeError:
                print("❌ 响应不是有效的JSON格式")
                print(f"📝 响应内容: {response.text[:200]}...")
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            try:
                error_data = response.json()
                print(f"🔍 错误信息: {error_data}")
            except:
                print(f"📝 响应文本: {response.text[:200]}...")
                
    except requests.exceptions.Timeout:
        print("⏰ 请求超时")
    except requests.exceptions.ConnectionError:
        print("🔌 连接错误")
    except Exception as e:
        print(f"❌ 请求失败: {e}")

def setup_test_data():
    """设置测试数据"""
    print("🔍 设置测试数据...")
    
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
    
    try:
        response = requests.post(search_url, json=search_data, headers=headers, timeout=60)
        if response.status_code == 200:
            print("✅ 测试数据设置成功")
            return True
        else:
            print(f"❌ 测试数据设置失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 设置测试数据时出错: {e}")
        return False

def test_all_analysis_apis():
    """测试所有分析API"""
    print("🚀 开始测试分析功能API...")
    
    # 先设置测试数据
    if not setup_test_data():
        print("❌ 无法设置测试数据，跳过API测试")
        return
    
    # 等待一下确保数据处理完成
    print("⏳ 等待数据处理...")
    time.sleep(3)
    
    base_url = "http://localhost:5000"
    test_query = "cancer treatment"
    
    # 测试数据
    test_data = {"query": test_query}
    
    # 测试各个API
    apis_to_test = [
        ("/api/analyze_research_status", "研究现状分析"),
        ("/api/review_topic_suggestion", "综述选题建议"),
        ("/api/research_topic_suggestion", "论著选题建议"),
        ("/api/generate_full_review", "完整综述生成")
    ]
    
    for endpoint, description in apis_to_test:
        url = base_url + endpoint
        test_api_endpoint(url, test_data, description)
        time.sleep(1)  # 避免请求过快

if __name__ == "__main__":
    test_all_analysis_apis()
    print("\n🏁 测试完成")
