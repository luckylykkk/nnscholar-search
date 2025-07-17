#!/usr/bin/env python3
"""
调试内容传递问题
"""

import requests
import json

def debug_content_issue():
    """调试为什么内容没有正确传递"""
    base_url = 'http://localhost:5001'
    
    session1 = requests.Session()
    
    # 1. 检索
    search_response = session1.post(f'{base_url}/api/search', json={
        'query': 'debug test',
        'mode': 'strategy'
    })
    
    search_data = search_response.json()
    session_id = search_data.get('session_id')
    print(f"Session ID: {session_id}")
    
    # 2. 启动任务
    task_response = session1.post(f'{base_url}/api/async/research_topic_suggestion', json={
        'query': 'debug test'
    })
    
    task_data = task_response.json()
    task_id = task_data.get('task_id')
    print(f"Task ID: {task_id}")
    
    # 3. 等待完成
    import time
    for i in range(20):
        status_response = session1.get(f'{base_url}/api/async/task/{task_id}/status')
        if status_response.status_code == 200:
            status_data = status_response.json()
            task_status = status_data.get('task', {}).get('status')
            
            if task_status == 'completed':
                break
            elif task_status == 'failed':
                print(f"Task failed")
                return
        time.sleep(2)
    
    # 4. 获取完整的result API响应
    result_response = session1.get(f'{base_url}/api/async/task/{task_id}/result')
    result_data = result_response.json()
    
    print("=== Result API Response ===")
    print(json.dumps(result_data, indent=2, ensure_ascii=False))
    
    result = result_data.get('result', {})
    
    # 5. 验证session缓存中的存储
    from utils.session_cache import get_papers_cache
    cache = get_papers_cache()
    cached_analysis = cache.get_analysis_result(session_id, 'research_topic')
    
    print(f"\n=== Cached Analysis Result ===")
    if cached_analysis:
        print(f"Paper count: {cached_analysis.get('paper_count')}")
        print(f"Content length: {len(cached_analysis.get('content', ''))}")
        print(f"Content preview: {cached_analysis.get('content', '')[:200]}...")
    else:
        print("No cached analysis result found")
    
    # 6. 使用新session访问分析页面，查看页面源码
    session2 = requests.Session()
    redirect_url = result_data.get('redirect_url', '')
    analysis_url = f"{base_url}{redirect_url}"
    
    print(f"\n=== Accessing analysis page ===")
    print(f"URL: {analysis_url}")
    
    analysis_response = session2.get(analysis_url)
    
    if analysis_response.status_code == 200:
        content = analysis_response.text
        
        # 查找关键部分
        import re
        
        # 查找论文数量
        paper_count_match = re.search(r'基于\s*(\d+)\s*篇相关文献', content)
        if paper_count_match:
            found_count = paper_count_match.group(1)
            print(f"Found paper count in HTML: {found_count}")
        
        # 查找分析内容区域
        content_match = re.search(r'<pre>(.*?)</pre>', content, re.DOTALL)
        if content_match:
            analysis_content = content_match.group(1)
            print(f"Found analysis content length: {len(analysis_content)}")
            print(f"Analysis content preview: {analysis_content[:200]}...")
        else:
            print("No analysis content found in <pre> tags")
            
        # 查找是否有恢复逻辑的内容
        if "基于URL参数恢复" in content:
            print("⚠️  Page triggered fallback recovery logic")
            
        # 检查实际的analysis_result变量值
        result_match = re.search(r'<pre>([^<]+)</pre>', content)
        if result_match:
            actual_result = result_match.group(1).strip()
            print(f"Actual analysis_result variable: '{actual_result[:100]}...'")
            
            # 检查是否包含真实的AI内容
            original_content = result.get('content', '')
            if original_content and original_content in actual_result:
                print("✅ Original AI content found in page")
            else:
                print("❌ Original AI content NOT found in page")
                print(f"Original content length: {len(original_content)}")
                print(f"Original content preview: {original_content[:100]}...")
    else:
        print(f"Failed to access analysis page: {analysis_response.status_code}")

if __name__ == "__main__":
    debug_content_issue()