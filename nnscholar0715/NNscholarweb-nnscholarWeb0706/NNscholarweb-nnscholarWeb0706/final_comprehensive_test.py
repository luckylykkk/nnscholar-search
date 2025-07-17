#!/usr/bin/env python3
"""
最终综合测试：验证所有修复是否工作
"""

import requests
import json
import time

def final_test():
    """最终综合测试"""
    base_url = 'http://localhost:5001'
    
    print("🎯 最终综合测试：验证跨session分析功能")
    print("=" * 50)
    
    # 第一步：检查搜索API响应格式
    session1 = requests.Session()
    
    print("1️⃣ 测试搜索API...")
    search_response = session1.post(f'{base_url}/api/search', json={
        'query': 'final test comprehensive',
        'mode': 'strategy'
    })
    
    print(f"   Status: {search_response.status_code}")
    
    if search_response.status_code == 200:
        search_data = search_response.json()
        
        # 检查响应结构
        if 'session_id' in search_data:
            session_id = search_data['session_id']
            print(f"✅ 搜索成功，session_id: {session_id}")
        elif 'data' in search_data:
            print(f"✅ 搜索成功，找到 {len(search_data['data'])} 篇文献")
            # 从cookie或其他地方获取session_id
            if 'Set-Cookie' in search_response.headers:
                print("   Cookie信息:", search_response.headers['Set-Cookie'])
            
            # 尝试从响应头获取session信息
            session_id = None
            
            # 进行一个简单的状态检查来获取session_id
            status_response = session1.get(f'{base_url}/api/status')
            if status_response.status_code == 200:
                # session_id应该在这个时候已经在cookie中了
                print("   Session已建立")
        else:
            print(f"❌ 搜索响应格式异常: {list(search_data.keys())}")
            return
    else:
        print(f"❌ 搜索失败: {search_response.status_code}")
        return
    
    # 第二步：启动异步任务
    print(f"\n2️⃣ 启动research_topic_suggestion任务...")
    
    task_response = session1.post(f'{base_url}/api/async/research_topic_suggestion', json={
        'query': 'final test comprehensive'
    })
    
    print(f"   Status: {task_response.status_code}")
    
    if task_response.status_code == 200:
        task_data = task_response.json()
        task_id = task_data.get('task_id')
        
        if task_id:
            print(f"✅ 任务启动成功，task_id: {task_id}")
        else:
            print(f"❌ 任务响应异常: {task_data}")
            return
    else:
        print(f"❌ 任务启动失败: {task_response.status_code}")
        try:
            error_data = task_response.json()
            print(f"   错误信息: {error_data}")
        except:
            pass
        return
    
    # 第三步：等待任务完成
    print(f"\n3️⃣ 等待任务完成...")
    
    max_attempts = 30
    for i in range(max_attempts):
        time.sleep(2)
        
        status_response = session1.get(f'{base_url}/api/async/task/{task_id}/status')
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            task_info = status_data.get('task', {})
            task_status = task_info.get('status')
            progress = task_info.get('progress', 0)
            
            print(f"   进度: {progress}% - 状态: {task_status}")
            
            if task_status == 'completed':
                print(f"✅ 任务完成")
                break
            elif task_status == 'failed':
                error_msg = task_info.get('error', '未知错误')
                print(f"❌ 任务失败: {error_msg}")
                return
        else:
            print(f"   获取状态失败: {status_response.status_code}")
    else:
        print(f"❌ 任务超时")
        return
    
    # 第四步：获取结果
    print(f"\n4️⃣ 获取任务结果...")
    
    result_response = session1.get(f'{base_url}/api/async/task/{task_id}/result')
    
    if result_response.status_code == 200:
        result_data = result_response.json()
        
        if result_data.get('success'):
            result = result_data.get('result', {})
            redirect_url = result_data.get('redirect_url', '')
            
            print(f"✅ 获取结果成功")
            print(f"   分析类型: {result.get('analysis_type')}")
            print(f"   论文数量: {result.get('paper_count')}")
            print(f"   内容长度: {len(result.get('content', ''))}")
            print(f"   重定向URL: {redirect_url}")
        else:
            print(f"❌ 结果获取失败: {result_data.get('error')}")
            return
    else:
        print(f"❌ 结果API调用失败: {result_response.status_code}")
        return
    
    # 第五步：跨session访问测试
    print(f"\n5️⃣ 跨session访问测试...")
    
    session2 = requests.Session()
    
    if redirect_url:
        analysis_url = f"{base_url}{redirect_url}"
        print(f"   访问URL: {analysis_url}")
        
        analysis_response = session2.get(analysis_url)
        
        if analysis_response.status_code == 200:
            content = analysis_response.text
            
            # 检查论文数量
            paper_count = result.get('paper_count', 0)
            if f"基于 {paper_count} 篇相关文献" in content:
                print(f"✅ 跨session论文数量显示正确: {paper_count} 篇")
                
                # 检查AI内容
                original_content = result.get('content', '')
                if original_content and original_content in content:
                    print(f"✅ 跨session AI内容完全正确")
                    print(f"🎉 所有测试通过！跨session分析功能完全正常！")
                    return True
                elif "基于URL参数恢复" in content:
                    print(f"❌ 跨session触发了备用逻辑")
                    print(f"   说明session缓存存储或检索有问题")
                else:
                    print(f"❌ 跨session AI内容状态未知")
            else:
                print(f"❌ 跨session论文数量显示错误")
        else:
            print(f"❌ 跨session访问失败: {analysis_response.status_code}")
    else:
        print(f"❌ 没有重定向URL")
    
    return False

if __name__ == "__main__":
    success = final_test()
    
    if success:
        print(f"\n🎊 测试结果：成功！")
        print(f"所有跨session分析功能都已修复并正常工作。")
    else:
        print(f"\n😞 测试结果：失败")
        print(f"还需要进一步调试和修复。")