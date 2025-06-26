#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试Excel导出功能（包含影响因子和分区）
"""

import sys
import os
from io import BytesIO
from datetime import datetime
import re

try:
    import pandas as pd
    print("✅ pandas 库导入成功")
except ImportError as e:
    print(f"❌ pandas 库导入失败: {e}")
    sys.exit(1)

def test_excel_generation():
    """测试Excel文档生成"""
    try:
        # 模拟文献数据
        papers_data = {
            'query': '测试查询',
            'papers': [
                {
                    'title': '测试文献标题1',
                    'authors': ['作者1', '作者2'],
                    'journal_info': {
                        'title': '测试期刊',
                        'impact_factor': 5.234,
                        'jcr_quartile': 1,
                        'cas_quartile': 2
                    },
                    'pub_year': '2023',
                    'relevance': 95.5,
                    'pmid': '12345678',
                    'doi': '10.1000/test1',
                    'abstract': '这是一个测试摘要，用于验证Excel导出功能是否正常工作。'
                },
                {
                    'title': '测试文献标题2',
                    'authors': ['作者3', '作者4'],
                    'journal_info': {
                        'title': '另一个测试期刊',
                        'impact_factor': 3.456,
                        'jcr_quartile': 2,
                        'cas_quartile': 3
                    },
                    'pub_year': '2024',
                    'relevance': 88.2,
                    'pmid': '87654321',
                    'doi': '10.1000/test2',
                    'abstract': '这是第二个测试摘要。'
                }
            ]
        }
        
        papers = papers_data.get('papers', [])
        query = papers_data.get('query', '未知查询')

        print(f"📊 开始生成Excel文档，包含 {len(papers)} 篇文献...")

        # 创建DataFrame
        df_data = []
        for i, paper in enumerate(papers, 1):
            # 处理JCR分区
            jcr_quartile = paper.get('journal_info', {}).get('jcr_quartile', '')
            jcr_display = f"Q{jcr_quartile}" if jcr_quartile else ''
            
            # 处理中科院分区
            cas_quartile = paper.get('journal_info', {}).get('cas_quartile', '')
            cas_display = f"{cas_quartile}区" if cas_quartile else ''
            
            df_data.append({
                '序号': i,
                '标题': paper.get('title', ''),
                '作者': ', '.join(paper.get('authors', [])),
                '期刊': paper.get('journal_info', {}).get('title', ''),
                '发表年份': paper.get('pub_year', ''),
                '影响因子': paper.get('journal_info', {}).get('impact_factor', ''),
                'JCR分区': jcr_display,
                '中科院分区': cas_display,
                '相关度': f"{paper.get('relevance', 0):.1f}%",
                'PMID': paper.get('pmid', ''),
                'DOI': paper.get('doi', ''),
                '摘要': paper.get('abstract', '')
            })

        df = pd.DataFrame(df_data)

        # 使用BytesIO创建内存中的Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='文献数据', index=False)

            # 获取工作表并设置格式
            worksheet = writer.sheets['文献数据']

            # 设置列宽
            column_widths = {
                'A': 8,   # 序号
                'B': 50,  # 标题
                'C': 30,  # 作者
                'D': 25,  # 期刊
                'E': 12,  # 年份
                'F': 12,  # 影响因子
                'G': 12,  # JCR分区
                'H': 12,  # 中科院分区
                'I': 12,  # 相关度
                'J': 15,  # PMID
                'K': 20,  # DOI
                'L': 80   # 摘要
            }

            for col, width in column_widths.items():
                worksheet.column_dimensions[col].width = width

        output.seek(0)
        file_content = output.getvalue()

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_query = re.sub(r'[^\w]', '_', query.replace('\n', ' ').replace('\r', ' ').strip())[:20]
        clean_query = re.sub(r'_+', '_', clean_query).strip('_')
        if not clean_query:
            clean_query = "literature_search"
        filename = f"test_papers_data_{clean_query}_{timestamp}.xlsx"

        print(f"✅ Excel文档生成成功！")
        print(f"📄 文件大小: {len(file_content)} 字节")
        print(f"📁 文件名: {filename}")
        print(f"📊 包含列: {list(df.columns)}")

        # 保存到文件进行验证
        with open(filename, 'wb') as f:
            f.write(file_content)
        
        print(f"💾 测试文件已保存到: {os.path.abspath(filename)}")
        
        # 验证数据内容
        print("\n📋 数据预览:")
        for i, row in df.iterrows():
            print(f"  文献 {i+1}:")
            print(f"    标题: {row['标题']}")
            print(f"    期刊: {row['期刊']}")
            print(f"    影响因子: {row['影响因子']}")
            print(f"    JCR分区: {row['JCR分区']}")
            print(f"    中科院分区: {row['中科院分区']}")
            print()
        
        return file_content, filename

    except Exception as e:
        print(f"❌ Excel文档生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None

if __name__ == "__main__":
    print("🧪 开始测试Excel导出功能...")
    test_excel_generation()
    print("🏁 测试完成")
