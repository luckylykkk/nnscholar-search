#!/usr/bin/env python3
"""
调试结果API的存储逻辑
"""

import requests
import json
import time

def debug_result_api():
    """调试结果API的session缓存存储"""
    base_url = 'http://localhost:5001'
    
    print("🔍 调试结果API的session缓存存储")
    print("=" * 50)
    
    session1 = requests.Session()
    
    # 完整流程
    print("1️⃣ 进行完整的检索和分析流程...")
    
    # 检索
    search_response = session1.post(f'{base_url}/api/search', json={
        'query': 'debug result api test',
        'mode': 'strategy'
    })
    
    search_data = search_response.json()
    session_id = search_data.get('session_id')
    print(f"   检索session_id: {session_id}")
    
    # 启动任务
    task_response = session1.post(f'{base_url}/api/async/research_topic_suggestion', json={
        'query': 'debug result api test'
    })
    
    task_data = task_response.json()
    task_id = task_data.get('task_id')
    print(f"   任务task_id: {task_id}")
    
    # 等待完成
    print("   等待任务完成...")
    for i in range(25):
        time.sleep(2)
        
        status_response = session1.get(f'{base_url}/api/async/task/{task_id}/status')
        if status_response.status_code == 200:
            status_data = status_response.json()
            task_info = status_data.get('task', {})
            task_status = task_info.get('status')
            
            if task_status == 'completed':
                print("   ✅ 任务完成")
                
                # 获取完整的task状态信息
                print(f"\n2️⃣ 检查任务状态信息...")
                print(f"   Task状态: {json.dumps(status_data, indent=2, ensure_ascii=False)}")
                
                break
            elif task_status == 'failed':
                print("   ❌ 任务失败")
                return
    else:
        print("   ❌ 任务超时")
        return
    
    # 调用结果API
    print(f"\n3️⃣ 调用结果API...")
    
    result_response = session1.get(f'{base_url}/api/async/task/{task_id}/result')
    
    if result_response.status_code == 200:
        result_data = result_response.json()
        print(f"   结果API响应: {json.dumps(result_data, indent=2, ensure_ascii=False)}")
        
        result = result_data.get('result', {})
        
        # 立即检查session缓存
        print(f"\n4️⃣ 立即检查session缓存...")
        
        try:
            from utils.session_cache import get_papers_cache
            cache = get_papers_cache()
            
            # 检查分析结果是否被存储
            cached_analysis = cache.get_analysis_result(session_id, 'research_topic')
            
            if cached_analysis:
                print(f"   ✅ 分析结果已存储到缓存")
                print(f"      论文数量: {cached_analysis.get('paper_count')}")
                print(f"      内容长度: {len(cached_analysis.get('content', ''))}")
            else:
                print(f"   ❌ 分析结果未存储到缓存")
                
                # 检查papers缓存
                papers_data = cache.get_papers(session_id)
                if papers_data:
                    print(f"   ✅ Papers缓存存在")
                    print(f"      论文数量: {len(papers_data.get('papers', []))}")
                else:
                    print(f"   ❌ Papers缓存也不存在")
                    
                # 手动尝试存储
                print(f"\n   🔧 手动尝试存储分析结果...")
                manual_success = cache.store_analysis_result(session_id, 'research_topic', result)
                
                if manual_success:
                    print(f"   ✅ 手动存储成功")
                    
                    # 立即检索验证
                    manual_retrieved = cache.get_analysis_result(session_id, 'research_topic')
                    if manual_retrieved:
                        print(f"   ✅ 手动存储后立即检索成功")
                    else:
                        print(f"   ❌ 手动存储后立即检索失败")
                else:
                    print(f"   ❌ 手动存储失败")
                    
        except Exception as e:
            print(f"   ❌ 检查缓存出错: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"   ❌ 结果API调用失败: {result_response.status_code}")

if __name__ == "__main__":
    debug_result_api()