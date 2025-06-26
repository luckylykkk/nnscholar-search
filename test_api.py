#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试NNScholar聊天界面API
"""

import requests
import json
import time

def test_search_api():
    """测试搜索API"""
    url = "http://localhost:5000/api/search"
    
    headers = {
        'Content-Type': 'application/json',
        'sid': 'test_session_123'
    }
    
    data = {
        "query": "糖尿病和CCTA相关研究",
        "mode": "single",
        "filters": {
            "year_start": 2020,
            "year_end": 2025,
            "papers_limit": 500
        }
    }
    
    print("🔍 开始测试文献检索...")
    print(f"查询内容: {data['query']}")
    print(f"时间范围: {data['filters']['year_start']}-{data['filters']['year_end']}")
    print(f"最大文献数: {data['filters']['papers_limit']}")
    print("-" * 50)
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=120)
        
        print(f"HTTP状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ 检索成功!")
                print(f"找到文献数量: {len(result.get('data', []))}")
                print(f"检索策略: {result.get('search_strategy', 'N/A')}")
                print(f"总计数量: {result.get('total_count', 'N/A')}")
                print(f"筛选后数量: {result.get('filtered_count', 'N/A')}")
                
                # 显示前3篇文献
                papers = result.get('data', [])
                if papers:
                    print("\n📚 前3篇文献:")
                    for i, paper in enumerate(papers[:3], 1):
                        print(f"{i}. {paper.get('title', 'N/A')}")
                        print(f"   作者: {', '.join(paper.get('authors', []))}")
                        print(f"   年份: {paper.get('pub_year', 'N/A')}")
                        print(f"   期刊: {paper.get('journal_info', {}).get('title', 'N/A')}")
                        print(f"   相关度: {paper.get('relevance', 'N/A')}%")
                        print()
                
                # 检查导出文件
                export_files = result.get('export_files', {})
                if export_files:
                    print("📁 导出文件:")
                    for file_type, filename in export_files.items():
                        print(f"   {file_type}: {filename}")
                
                return result
            else:
                print(f"❌ 检索失败: {result.get('error', '未知错误')}")
                return None
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            print(f"响应内容: {response.text}")
            return None
            
    except requests.exceptions.Timeout:
        print("⏰ 请求超时")
        return None
    except requests.exceptions.ConnectionError:
        print("🔌 连接错误，请确保应用正在运行")
        return None
    except Exception as e:
        print(f"❌ 发生错误: {str(e)}")
        return None

def test_research_status_api(titles, query):
    """测试研究现状分析API"""
    url = "http://localhost:5000/api/analyze_research_status"
    
    headers = {
        'Content-Type': 'application/json',
        'sid': 'test_session_123'
    }
    
    data = {
        "query": query,
        "titles": titles[:50],  # 限制50个标题
        "paper_count": len(titles)
    }
    
    print("\n🧠 开始测试研究现状分析...")
    print(f"分析标题数量: {len(data['titles'])}")
    print("-" * 50)
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        
        print(f"HTTP状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print("✅ 分析成功!")
                print(f"分析了 {result.get('analyzed_papers', 0)} 篇文献")
                print(f"总文献数: {result.get('total_papers', 0)}")
                print("\n📊 研究现状分析结果:")
                print(result.get('analysis', '无分析结果'))
                return result
            else:
                print(f"❌ 分析失败: {result.get('error', '未知错误')}")
                return None
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            print(f"响应内容: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 发生错误: {str(e)}")
        return None

if __name__ == "__main__":
    print("🚀 NNScholar API 测试开始")
    print("=" * 60)
    
    # 测试搜索API
    search_result = test_search_api()
    
    if search_result and search_result.get('success'):
        # 提取文献标题进行研究现状分析
        papers = search_result.get('data', [])
        titles = [paper.get('title', '') for paper in papers if paper.get('title')]
        
        if titles:
            # 测试研究现状分析API
            test_research_status_api(titles, "糖尿病和CCTA相关研究")
    
    print("\n" + "=" * 60)
    print("🏁 测试完成")
