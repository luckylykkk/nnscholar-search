#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试文件名修复
"""

import re
from datetime import datetime

def test_filename_generation():
    """测试文件名生成逻辑"""
    
    # 测试包含换行符的查询
    test_queries = [
        "cancer treatment\nwith immunotherapy",
        "diabetes\r\nmanagement",
        "covid-19\nvaccine\reffectiveness",
        "machine learning\n\nin healthcare",
        "特殊字符!@#$%^&*()",
        "",
        "   ",
        "normal query",
        "very long query that should be truncated because it exceeds the maximum length limit"
    ]
    
    print("🧪 测试文件名生成逻辑...")
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n测试 {i}: '{repr(query)}'")
        
        # Word文件名生成逻辑
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_query = re.sub(r'[^\w]', '_', query.replace('\n', ' ').replace('\r', ' ').strip())[:20]
        clean_query = re.sub(r'_+', '_', clean_query).strip('_')
        if not clean_query:
            clean_query = "literature_search"
        word_filename = f"research_report_{clean_query}_{timestamp}.docx"
        
        # Excel文件名生成逻辑
        excel_filename = f"papers_data_{clean_query}_{timestamp}.xlsx"
        
        print(f"  Word文件名: {word_filename}")
        print(f"  Excel文件名: {excel_filename}")
        
        # 检查是否包含换行符
        has_newline = '\n' in word_filename or '\r' in word_filename
        print(f"  包含换行符: {'❌ 是' if has_newline else '✅ 否'}")
        
        # 检查文件名长度
        print(f"  Word文件名长度: {len(word_filename)}")
        print(f"  Excel文件名长度: {len(excel_filename)}")

def test_http_header_safety():
    """测试HTTP头安全性"""
    print("\n🔒 测试HTTP头安全性...")
    
    # 模拟包含换行符的查询
    dangerous_query = "test\nquery\rwith\n\rlinebreaks"
    
    # 应用修复逻辑
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_query = re.sub(r'[^\w]', '_', dangerous_query.replace('\n', ' ').replace('\r', ' ').strip())[:20]
    clean_query = re.sub(r'_+', '_', clean_query).strip('_')
    if not clean_query:
        clean_query = "literature_search"
    filename = f"research_report_{clean_query}_{timestamp}.docx"
    
    print(f"原始查询: {repr(dangerous_query)}")
    print(f"清理后文件名: {filename}")
    
    # 检查是否安全用于HTTP头
    is_safe = '\n' not in filename and '\r' not in filename
    print(f"HTTP头安全: {'✅ 是' if is_safe else '❌ 否'}")
    
    # 模拟HTTP Content-Disposition头
    content_disposition = f'attachment; filename="{filename}"'
    print(f"Content-Disposition: {content_disposition}")
    
    return is_safe

if __name__ == "__main__":
    test_filename_generation()
    is_safe = test_http_header_safety()
    
    print(f"\n🏁 测试完成，文件名生成{'✅ 安全' if is_safe else '❌ 不安全'}")
