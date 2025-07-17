#!/usr/bin/env python3
"""
调试session数据问题

验证异步分析结果的session存储和读取逻辑
"""

import sys
import os
import json

# 添加项目路径
sys.path.insert(0, '/mnt/h/nnscholar-search-main')

def debug_session_data():
    """调试session数据存储问题"""
    
    print("🔍 Session数据调试分析")
    print("=" * 50)
    
    # 检查异步任务处理器的结果格式
    print("\n📋 检查异步任务处理器的结果格式:")
    
    from services.academic_analysis_handlers import handle_research_topic_analysis
    from services.async_task_service import AsyncTask, TaskStatus
    
    # 创建一个模拟任务
    task_data = {
        'query': 'machine learning',
        'session_id': 'test_session_123'
    }
    
    # 创建AsyncTask实例
    test_task = AsyncTask('test_task_id', 'research_topic_analysis', task_data)
    
    print(f"✅ 任务创建成功: {test_task.task_id}")
    print(f"📝 任务类型: {test_task.task_type}")
    print(f"📊 任务数据: {test_task.task_data}")
    
    # 模拟任务处理（会失败，但我们可以看到错误结果的格式）
    try:
        result = handle_research_topic_analysis(test_task)
        print(f"✅ 任务结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"⚠️  任务执行失败（预期的）: {e}")
        
        # 检查任务状态
        print(f"📋 任务状态: {test_task.status}")
        print(f"📈 任务进度: {test_task.progress}%")
        print(f"💬 任务消息: {test_task.message}")
        print(f"❌ 任务错误: {test_task.error}")
    
    print("\n🔗 检查API路由的session存储逻辑:")
    
    # 检查路由文件中的session key格式
    api_file = '/mnt/h/nnscholar-search-main/routes/api_routes.py'
    with open(api_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找所有session存储操作
    import re
    session_patterns = re.findall(r"session\['([^']+)'\]\s*=", content)
    
    print("📚 发现的session keys:")
    for i, key in enumerate(session_patterns, 1):
        print(f"  {i}. {key}")
    
    # 检查新旧API的session key冲突
    print("\n⚠️  潜在的session key冲突:")
    async_keys = [key for key in session_patterns if 'result' in key]
    unique_keys = set(async_keys)
    
    for key in unique_keys:
        count = async_keys.count(key)
        if count > 1:
            print(f"  🔴 冲突: '{key}' 被使用了 {count} 次")
        else:
            print(f"  🟢 正常: '{key}' 被使用了 {count} 次")
    
    print("\n🎯 问题分析和建议:")
    print("1. 检查是否存在旧的同步API和新的异步API使用相同的session key")
    print("2. 验证session数据的格式是否一致")
    print("3. 确认前端跳转时session数据是否正确传递")
    
    # 检查模板期望的数据格式
    print("\n📄 检查模板期望的数据格式:")
    template_file = '/mnt/h/nnscholar-search-main/templates/academic_analysis.html'
    with open(template_file, 'r', encoding='utf-8') as f:
        template_content = f.read()
    
    # 查找模板中使用的变量
    template_vars = re.findall(r'\{\{\s*([^}]+)\s*\}\}', template_content)
    
    print("📋 模板中使用的变量:")
    for var in set(template_vars):
        var = var.strip()
        if not var.startswith('analysis_type') and not var.startswith('if') and not var.startswith('elif'):
            print(f"  - {var}")
    
    print("\n🔧 建议的修复方案:")
    print("1. 清理旧的同步API中的session存储逻辑，避免冲突")
    print("2. 确保异步API的结果格式完全符合模板期望")
    print("3. 添加session数据验证和默认值处理")
    print("4. 考虑在前端跳转前验证session数据的完整性")

if __name__ == "__main__":
    debug_session_data()