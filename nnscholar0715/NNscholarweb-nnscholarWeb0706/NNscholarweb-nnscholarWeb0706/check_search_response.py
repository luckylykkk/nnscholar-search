#!/usr/bin/env python3
"""
检查搜索API的响应格式
"""

import requests
import json

def check_search_response():
    """检查搜索API的响应格式"""
    base_url = 'http://localhost:5001'
    
    print("🔍 检查搜索API响应格式")
    print("=" * 40)
    
    session1 = requests.Session()
    
    # 调用搜索API
    search_response = session1.post(f'{base_url}/api/search', json={
        'query': 'response format test',
        'mode': 'strategy'
    })
    
    print(f"状态码: {search_response.status_code}")
    print(f"响应头: {dict(search_response.headers)}")
    
    if search_response.status_code == 200:
        try:
            search_data = search_response.json()
            print(f"\n响应结构:")
            print(f"顶级键: {list(search_data.keys())}")
            
            # 检查是否有session_id
            if 'session_id' in search_data:
                print(f"session_id: {search_data['session_id']}")
            else:
                print("❌ 没有session_id字段")
            
            # 检查是否有data字段
            if 'data' in search_data:
                data = search_data['data']
                print(f"data类型: {type(data)}")
                if isinstance(data, list):
                    print(f"data长度: {len(data)}")
                    if data:
                        print(f"第一项键: {list(data[0].keys()) if data[0] else 'None'}")
            
            # 检查是否有其他有用的字段
            for key, value in search_data.items():
                if key not in ['data']:
                    print(f"{key}: {value}")
                    
        except json.JSONDecodeError as e:
            print(f"❌ JSON解析失败: {e}")
            print(f"原始响应: {search_response.text[:500]}...")
    else:
        print(f"❌ 请求失败")
        print(f"响应内容: {search_response.text[:500]}...")

    # 检查搜索API的路由定义
    print(f"\n🔍 检查搜索API返回格式...")
    
    # 可能search API只返回数据，session_id在cookie中
    print(f"Cookies: {dict(search_response.cookies)}")

if __name__ == "__main__":
    check_search_response()