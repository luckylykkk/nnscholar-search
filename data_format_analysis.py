"""
数据格式分析脚本
详细分析不同数据库返回的数据格式差异
"""

import json
from typing import Dict, List, Any

def analyze_openalex_format() -> Dict[str, Any]:
    """分析OpenAlex数据格式"""
    return {
        'database': 'OpenAlex',
        'api_format': 'JSON',
        'main_fields': {
            'id': 'OpenAlex唯一标识符',
            'display_name': '文献标题',
            'publication_year': '发表年份',
            'authorships': '作者信息列表',
            'abstract_inverted_index': '摘要倒排索引',
            'primary_location': '主要发表位置',
            'open_access': '开放获取信息',
            'cited_by_count': '被引用次数',
            'concepts': '概念标签',
            'type': '文献类型'
        },
        'nested_structures': {
            'authorships': ['author', 'institutions', 'countries'],
            'primary_location': ['source', 'is_oa', 'landing_page_url'],
            'open_access': ['is_oa', 'oa_date', 'oa_url']
        },
        'unique_features': [
            '倒排索引格式的摘要',
            '详细的开放获取信息',
            '机构和国家信息',
            '概念标签系统'
        ],
        'data_quality': {
            'title_coverage': '95%+',
            'abstract_coverage': '60-70%',
            'author_coverage': '90%+',
            'doi_coverage': '80%+'
        }
    }

def analyze_arxiv_format() -> Dict[str, Any]:
    """分析arXiv数据格式"""
    return {
        'database': 'arXiv',
        'api_format': 'XML (Atom feed)',
        'main_fields': {
            'id': 'arXiv ID',
            'title': '文献标题',
            'summary': '摘要',
            'author': '作者列表',
            'published': '发布日期',
            'updated': '更新日期',
            'category': '分类标签',
            'link': '文献链接'
        },
        'xml_namespaces': [
            'atom: http://www.w3.org/2005/Atom',
            'arxiv: http://arxiv.org/schemas/atom'
        ],
        'unique_features': [
            'XML格式返回',
            '分类代码系统 (cs.AI, math.ST等)',
            '版本控制 (v1, v2等)',
            '预印本特性'
        ],
        'data_quality': {
            'title_coverage': '100%',
            'abstract_coverage': '100%',
            'author_coverage': '100%',
            'doi_coverage': '30-40%'
        }
    }

def analyze_semantic_scholar_format() -> Dict[str, Any]:
    """分析Semantic Scholar数据格式"""
    return {
        'database': 'Semantic Scholar',
        'api_format': 'JSON',
        'main_fields': {
            'paperId': 'Semantic Scholar ID',
            'title': '文献标题',
            'abstract': '摘要',
            'year': '发表年份',
            'authors': '作者列表',
            'venue': '发表场所',
            'citationCount': '引用次数',
            'influentialCitationCount': '有影响力的引用次数',
            'isOpenAccess': '是否开放获取',
            'fieldsOfStudy': '研究领域',
            's2FieldsOfStudy': 'S2研究领域分类'
        },
        'nested_structures': {
            'authors': ['authorId', 'name'],
            'publicationVenue': ['id', 'name', 'type'],
            's2FieldsOfStudy': ['category', 'source']
        },
        'unique_features': [
            'AI增强的语义分析',
            '有影响力的引用计数',
            'S2特有的领域分类',
            '作者消歧处理'
        ],
        'data_quality': {
            'title_coverage': '100%',
            'abstract_coverage': '70-80%',
            'author_coverage': '95%+',
            'citation_coverage': '90%+'
        }
    }

def analyze_doaj_format() -> Dict[str, Any]:
    """分析DOAJ数据格式"""
    return {
        'database': 'DOAJ',
        'api_format': 'JSON',
        'main_fields': {
            'id': 'DOAJ ID',
            'bibjson.title': '文献标题',
            'bibjson.abstract': '摘要',
            'bibjson.author': '作者列表',
            'bibjson.year': '发表年份',
            'bibjson.journal': '期刊信息',
            'bibjson.subject': '主题分类',
            'bibjson.link': '链接信息',
            'bibjson.identifier': '标识符 (DOI等)'
        },
        'nested_structures': {
            'bibjson': '所有文献信息都在bibjson字段中',
            'journal': ['title', 'issns', 'publisher'],
            'subject': ['scheme', 'term', 'code']
        },
        'unique_features': [
            '专注开放获取期刊',
            '多语言支持',
            '详细的期刊信息',
            '主题分类系统'
        ],
        'data_quality': {
            'title_coverage': '100%',
            'abstract_coverage': '80-90%',
            'author_coverage': '90%+',
            'doi_coverage': '95%+'
        }
    }

def analyze_crossref_format() -> Dict[str, Any]:
    """分析Crossref数据格式"""
    return {
        'database': 'Crossref',
        'api_format': 'JSON',
        'main_fields': {
            'DOI': 'DOI标识符',
            'title': '文献标题 (数组格式)',
            'author': '作者列表',
            'published-print': '印刷版发表日期',
            'published-online': '在线发表日期',
            'container-title': '期刊名称',
            'publisher': '出版商',
            'type': '文献类型',
            'is-referenced-by-count': '被引用次数',
            'abstract': '摘要 (较少)'
        },
        'nested_structures': {
            'author': ['given', 'family', 'ORCID'],
            'published-print': ['date-parts'],
            'funder': ['name', 'DOI', 'award']
        },
        'unique_features': [
            '权威的DOI注册信息',
            '详细的出版商信息',
            '资助信息',
            '标准化的元数据'
        ],
        'data_quality': {
            'title_coverage': '100%',
            'abstract_coverage': '20-30%',
            'author_coverage': '95%+',
            'doi_coverage': '100%'
        }
    }

def generate_comparison_table() -> str:
    """生成数据格式对比表"""
    
    formats = [
        analyze_openalex_format(),
        analyze_arxiv_format(),
        analyze_semantic_scholar_format(),
        analyze_doaj_format(),
        analyze_crossref_format()
    ]
    
    comparison = []
    comparison.append("=" * 100)
    comparison.append("多数据库数据格式对比分析")
    comparison.append("=" * 100)
    
    # 基本信息对比
    comparison.append("\n1. 基本信息对比:")
    comparison.append("-" * 80)
    comparison.append(f"{'数据库':<15} {'API格式':<10} {'标题覆盖':<10} {'摘要覆盖':<10} {'DOI覆盖':<10}")
    comparison.append("-" * 80)
    
    for fmt in formats:
        db_name = fmt['database']
        api_format = fmt['api_format']
        title_cov = fmt['data_quality']['title_coverage']
        abstract_cov = fmt['data_quality']['abstract_coverage']
        doi_cov = fmt['data_quality']['doi_coverage']
        
        comparison.append(f"{db_name:<15} {api_format:<10} {title_cov:<10} {abstract_cov:<10} {doi_cov:<10}")
    
    # 独特特性对比
    comparison.append("\n\n2. 独特特性对比:")
    comparison.append("-" * 80)
    
    for fmt in formats:
        comparison.append(f"\n{fmt['database']}:")
        for feature in fmt['unique_features']:
            comparison.append(f"  • {feature}")
    
    # 数据结构对比
    comparison.append("\n\n3. 主要字段对比:")
    comparison.append("-" * 80)
    
    # 标题字段
    comparison.append("\n标题字段:")
    for fmt in formats:
        title_field = None
        for field, desc in fmt['main_fields'].items():
            if '标题' in desc:
                title_field = field
                break
        comparison.append(f"  {fmt['database']}: {title_field}")
    
    # 作者字段
    comparison.append("\n作者字段:")
    for fmt in formats:
        author_field = None
        for field, desc in fmt['main_fields'].items():
            if '作者' in desc:
                author_field = field
                break
        comparison.append(f"  {fmt['database']}: {author_field}")
    
    # 摘要字段
    comparison.append("\n摘要字段:")
    for fmt in formats:
        abstract_field = None
        for field, desc in fmt['main_fields'].items():
            if '摘要' in desc:
                abstract_field = field
                break
        comparison.append(f"  {fmt['database']}: {abstract_field}")
    
    # 规范化挑战
    comparison.append("\n\n4. 数据规范化挑战:")
    comparison.append("-" * 80)
    
    challenges = {
        'OpenAlex': ['倒排索引摘要需要重构', '复杂的嵌套结构', '概念标签映射'],
        'arXiv': ['XML格式解析', '分类代码转换', '版本信息处理'],
        'Semantic Scholar': ['字段名称差异', 'S2特有分类', '作者ID映射'],
        'DOAJ': ['bibjson嵌套结构', '多语言处理', '主题分类转换'],
        'Crossref': ['数组格式标题', '日期格式多样', '摘要覆盖率低']
    }
    
    for db, challenge_list in challenges.items():
        comparison.append(f"\n{db}:")
        for challenge in challenge_list:
            comparison.append(f"  • {challenge}")
    
    comparison.append("\n" + "=" * 100)
    comparison.append("分析完成")
    comparison.append("=" * 100)
    
    return "\n".join(comparison)

def save_format_analysis():
    """保存格式分析结果"""
    
    formats = {
        'openalex': analyze_openalex_format(),
        'arxiv': analyze_arxiv_format(),
        'semantic_scholar': analyze_semantic_scholar_format(),
        'doaj': analyze_doaj_format(),
        'crossref': analyze_crossref_format()
    }
    
    # 保存详细分析
    with open('database_formats_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(formats, f, ensure_ascii=False, indent=2)
    
    # 保存对比表
    comparison_table = generate_comparison_table()
    with open('database_formats_comparison.txt', 'w', encoding='utf-8') as f:
        f.write(comparison_table)
    
    print("数据格式分析已保存:")
    print("  • database_formats_analysis.json - 详细分析")
    print("  • database_formats_comparison.txt - 对比表")
    
    return comparison_table

def main():
    """主函数"""
    print("开始数据格式分析...")
    
    # 生成并显示对比表
    comparison_table = save_format_analysis()
    print(comparison_table)
    
    return True

if __name__ == "__main__":
    main()
