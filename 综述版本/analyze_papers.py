import pandas as pd
import os
from datetime import datetime
import numpy as np
from collections import Counter
import re

def clean_text(text):
    if pd.isna(text):
        return ""
    return str(text).strip()

def extract_keywords(text):
    # 预定义的关键词列表
    keywords = [
        'artificial intelligence', 'AI', 'machine learning', 'ML',
        'deep learning', 'DL', 'large language model', 'LLM',
        'natural language processing', 'NLP', 'neural network',
        'deep neural network', 'CNN', 'transformer', 'GPT',
        'BERT', 'radiomics', 'computer vision', 'image analysis',
        'segmentation', 'classification', 'detection'
    ]
    
    text = text.lower()
    found_keywords = []
    for keyword in keywords:
        if keyword.lower() in text:
            found_keywords.append(keyword)
    return found_keywords

def export_to_text(df, output_file):
    """将DataFrame转换为易读的文本格式"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('文献清单\n')
        f.write('=' * 100 + '\n\n')
        
        # 按相关度排序
        df['相关度数值'] = df['相关度'].apply(lambda x: float(str(x).rstrip('%')) if pd.notnull(x) else 0)
        df = df.sort_values('相关度数值', ascending=False)
        
        for idx, row in df.iterrows():
            f.write(f'文献 {idx+1}\n')
            f.write('-' * 100 + '\n')
            f.write(f'标题：{clean_text(row["标题"])}\n')
            f.write(f'作者：{clean_text(row["作者"])}\n')
            f.write(f'发表年份：{row["发表年份"]}\n')
            f.write(f'期刊名称：{clean_text(row["期刊名称"])}\n')
            f.write(f'影响因子：{row["影响因子"]}\n')
            f.write(f'JCR分区：{row["JCR分区"]}\n')
            f.write(f'CAS分区：{row["CAS分区"]}\n')
            f.write(f'相关度：{row["相关度"]}\n')
            f.write(f'PMID：{row["PMID"]}\n')
            f.write(f'DOI：{row["DOI"]}\n\n')
            f.write('摘要：\n')
            f.write(f'{clean_text(row["摘要"])}\n')
            f.write('=' * 100 + '\n\n')

def analyze_papers(file_path):
    try:
        # 读取Excel文件
        df = pd.read_excel(file_path)
        print(f"成功读取文件，共{len(df)}条记录")
        
        # 创建输出目录
        output_dir = os.path.dirname(file_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 导出文本格式的文献清单
        text_file = os.path.join(output_dir, f'papers_list_{timestamp}.txt')
        export_to_text(df, text_file)
        print(f"文献清单已导出至：{text_file}")
        
        # 创建分析报告文件名
        report_file = os.path.join(output_dir, f'analysis_report_{timestamp}.txt')
        
        # 数据清洗
        df['标题'] = df['标题'].apply(clean_text)
        df['摘要'] = df['摘要'].apply(clean_text)
        df['作者'] = df['作者'].apply(clean_text)
        
        # 提取关键词
        df['关键词'] = df.apply(lambda x: extract_keywords(str(x['标题']) + ' ' + str(x['摘要'])), axis=1)
        
        # 基本统计信息
        total_papers = len(df)
        avg_if = pd.to_numeric(df['影响因子'].replace('N/A', None), errors='coerce').mean()
        
        # 按年份分布
        year_dist = df['发表年份'].value_counts().sort_index()
        
        # 相关度分析
        df['相关度数值'] = df['相关度'].apply(lambda x: float(str(x).rstrip('%')) if pd.notnull(x) else 0)
        high_relevance = df[df['相关度数值'] >= 80].copy()
        
        # 关键词统计
        all_keywords = [kw for keywords in df['关键词'] for kw in keywords]
        keyword_freq = Counter(all_keywords)
        
        # 生成分析报告
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write('Radiology期刊大语言模型研究文献分析报告\n')
            f.write('=' * 50 + '\n\n')
            
            # 1. 总体概况
            f.write('1. 总体概况\n')
            f.write('-' * 20 + '\n')
            f.write(f'总文献数：{total_papers}篇\n')
            if not np.isnan(avg_if):
                f.write(f'平均影响因子：{avg_if:.2f}\n')
            else:
                f.write('平均影响因子：数据不可用\n')
            f.write(f'文献相关度分布：\n')
            f.write(f'- 高相关（≥80%）：{len(high_relevance)}篇\n')
            f.write(f'- 中相关（50-79%）：{len(df[(df["相关度数值"] >= 50) & (df["相关度数值"] < 80)])}篇\n')
            f.write(f'- 低相关（<50%）：{len(df[df["相关度数值"] < 50])}篇\n\n')
            
            # 2. 年份分布
            f.write('2. 发表年份分布\n')
            f.write('-' * 20 + '\n')
            for year, count in year_dist.items():
                f.write(f'{year}年：{count}篇\n')
            f.write('\n')
            
            # 3. 研究主题分析
            f.write('3. 研究主题分析\n')
            f.write('-' * 20 + '\n')
            f.write('主要研究关键词频率（出现3次以上）：\n')
            for keyword, freq in keyword_freq.most_common():
                if freq >= 3:
                    f.write(f'- {keyword}: {freq}次\n')
            f.write('\n')
            
            # 4. 高相关文献详细分析
            f.write('4. 高相关文献详细分析（相关度≥80%）\n')
            f.write('-' * 20 + '\n')
            for idx, paper in high_relevance.sort_values('相关度数值', ascending=False).iterrows():
                f.write(f'文献 {idx+1}:\n')
                f.write(f'标题：{paper["标题"]}\n')
                f.write(f'作者：{paper["作者"]}\n')
                f.write(f'发表年份：{paper["发表年份"]}\n')
                f.write(f'影响因子：{paper["影响因子"]}\n')
                f.write(f'相关度：{paper["相关度"]}\n')
                f.write(f'关键词：{", ".join(paper["关键词"])}\n')
                f.write(f'摘要：{paper["摘要"]}\n')
                f.write('-' * 50 + '\n')
            
            # 5. 研究趋势分析
            f.write('\n5. 研究趋势分析\n')
            f.write('-' * 20 + '\n')
            
            # 按年份统计关键词趋势
            f.write('近年研究热点演变：\n')
            years = sorted(year_dist.index)
            for year in years[-3:]:  # 分析最近三年
                year_papers = df[df['发表年份'] == year]
                year_keywords = [kw for keywords in year_papers['关键词'] for kw in keywords]
                year_freq = Counter(year_keywords)
                f.write(f'\n{year}年热点关键词：\n')
                for kw, freq in year_freq.most_common(5):
                    f.write(f'- {kw}: {freq}次\n')
            
            # 6. 研究展望
            f.write('\n6. 研究展望\n')
            f.write('-' * 20 + '\n')
            f.write('基于文献分析，未来研究方向可能包括：\n')
            # 分析最新文献中提到的未来研究方向
            recent_papers = df[df['发表年份'] == max(years)]
            future_keywords = set()
            for abstract in recent_papers['摘要']:
                if 'future' in str(abstract).lower() or 'potential' in str(abstract).lower():
                    future_keywords.update(extract_keywords(str(abstract)))
            for kw in future_keywords:
                f.write(f'- {kw}\n')
        
        print(f'分析报告已生成：{report_file}')
        return report_file, text_file
        
    except Exception as e:
        print(f"分析过程中出现错误：{str(e)}")
        import traceback
        traceback.print_exc()
        return None, None

if __name__ == '__main__':
    # 分析初始文献
    initial_file = 'exports/ai.xlsx'
    report_file, text_file = analyze_papers(initial_file)
    if report_file and text_file:
        print(f'分析完成！\n分析报告：{report_file}\n文献清单：{text_file}') 