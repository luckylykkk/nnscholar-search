#!/usr/bin/env python3
"""
统计各期刊近一年的平均审稿周期
"""

import requests
import xml.etree.ElementTree as ET
import json
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any, Optional
import statistics

def analyze_journal_review_cycles():
    """分析各期刊的审稿周期"""
    
    print("=" * 100)
    print("期刊审稿周期统计分析")
    print("=" * 100)
    
    # 获取近一年的高影响因子期刊文献
    journals_to_analyze = [
        "Nature",
        "Science", 
        "Cell",
        "Nature Reviews Molecular Cell Biology",
        "Nature Medicine",
        "Nature Biotechnology",
        "Nature Genetics",
        "Nature Immunology",
        "Nature Neuroscience",
        "Nature Cell Biology",
        "The Lancet",
        "New England Journal of Medicine",
        "JAMA",
        "Nature Communications",
        "PNAS"
    ]
    
    all_journal_stats = {}
    
    for journal in journals_to_analyze:
        print(f"\n📊 分析期刊: {journal}")
        print("-" * 60)
        
        stats = analyze_single_journal(journal)
        if stats:
            all_journal_stats[journal] = stats
            print_journal_stats(journal, stats)
        else:
            print(f"❌ 未能获取 {journal} 的数据")
    
    # 生成综合报告
    generate_comprehensive_report(all_journal_stats)

def analyze_single_journal(journal_name: str, max_papers: int = 100) -> Optional[Dict[str, Any]]:
    """分析单个期刊的审稿周期"""
    
    # 构建检索式 - 近一年的文献
    search_query = f'("{journal_name}"[Journal]) AND (("2024/01/01"[Date - Create] : "2025/12/31"[Date - Create]))'
    
    try:
        # 搜索文献
        pmids = search_journal_papers(search_query, max_papers)
        if not pmids:
            return None
        
        print(f"   找到 {len(pmids)} 篇文献")
        
        # 获取详细信息
        papers = fetch_papers_with_dates(pmids)
        if not papers:
            return None
        
        print(f"   成功解析 {len(papers)} 篇文献的时间信息")
        
        # 计算审稿周期
        stats = calculate_review_cycles(papers)
        stats['total_papers'] = len(papers)
        stats['journal_name'] = journal_name
        
        return stats
        
    except Exception as e:
        print(f"   ❌ 分析失败: {e}")
        return None

def search_journal_papers(query: str, max_results: int) -> List[str]:
    """搜索期刊文献"""
    try:
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            'db': 'pubmed',
            'term': query,
            'retmax': max_results,
            'retmode': 'xml',
            'tool': 'NNScholar',
            'email': 'test@nnscholar.com'
        }
        
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        pmids = [id_elem.text for id_elem in root.findall('.//Id')]
        
        return pmids
        
    except Exception as e:
        print(f"   搜索失败: {e}")
        return []

def fetch_papers_with_dates(pmids: List[str]) -> List[Dict[str, Any]]:
    """获取文献的详细时间信息"""
    try:
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            'db': 'pubmed',
            'id': ','.join(pmids),
            'retmode': 'xml',
            'rettype': 'abstract',
            'tool': 'NNScholar',
            'email': 'test@nnscholar.com'
        }
        
        response = requests.get(base_url, params=params, timeout=120)
        response.raise_for_status()
        
        return parse_papers_dates(response.content)
        
    except Exception as e:
        print(f"   获取详细信息失败: {e}")
        return []

def parse_papers_dates(xml_content: bytes) -> List[Dict[str, Any]]:
    """解析文献的时间信息"""
    papers = []
    
    try:
        root = ET.fromstring(xml_content)
        
        for article_elem in root.findall('.//PubmedArticle'):
            paper_dates = extract_paper_dates(article_elem)
            if paper_dates:
                papers.append(paper_dates)
                
    except ET.ParseError as e:
        print(f"   XML解析失败: {e}")
    
    return papers

def extract_paper_dates(article_elem) -> Optional[Dict[str, Any]]:
    """提取单篇文献的时间信息"""
    try:
        paper = {}
        
        # 基本信息
        medline_citation = article_elem.find('.//MedlineCitation')
        if medline_citation is not None:
            paper['pmid'] = get_text(medline_citation.find('.//PMID'))
        
        # 文章标题
        article = article_elem.find('.//Article')
        if article is not None:
            paper['title'] = get_text(article.find('.//ArticleTitle'))[:100] + "..."
        
        # 提取各种日期
        dates = {}
        
        # 从PubmedData/History中提取日期
        pubmed_data = article_elem.find('.//PubmedData')
        if pubmed_data is not None:
            history = pubmed_data.find('.//History')
            if history is not None:
                for pub_date in history.findall('.//PubMedPubDate'):
                    status = pub_date.get('PubStatus', '')
                    date_obj = parse_date_element(pub_date)
                    if date_obj:
                        dates[status] = date_obj
        
        # 从期刊发表日期中提取
        if article is not None:
            journal = article.find('.//Journal')
            if journal is not None:
                journal_issue = journal.find('.//JournalIssue')
                if journal_issue is not None:
                    pub_date = journal_issue.find('.//PubDate')
                    if pub_date is not None:
                        date_obj = parse_date_element(pub_date)
                        if date_obj:
                            dates['published'] = date_obj
        
        paper['dates'] = dates
        
        # 只返回有足够日期信息的文献
        if len(dates) >= 2:
            return paper
        
        return None
        
    except Exception as e:
        return None

def parse_date_element(date_elem) -> Optional[datetime]:
    """解析日期元素"""
    try:
        year = get_text(date_elem.find('.//Year'))
        month = get_text(date_elem.find('.//Month'))
        day = get_text(date_elem.find('.//Day'))
        
        if not year:
            return None
        
        # 处理月份
        if month:
            try:
                month_num = int(month)
            except ValueError:
                # 处理月份名称
                month_names = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                month_num = month_names.get(month[:3], 1)
        else:
            month_num = 1
        
        day_num = int(day) if day else 1
        
        return datetime(int(year), month_num, day_num)
        
    except (ValueError, TypeError):
        return None

def calculate_review_cycles(papers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """计算审稿周期统计"""
    
    review_cycles = []  # 从接收到接受的天数
    publication_cycles = []  # 从接受到发表的天数
    total_cycles = []  # 从接收到发表的总天数
    
    date_stats = {
        'received_count': 0,
        'accepted_count': 0,
        'published_count': 0,
        'complete_cycle_count': 0
    }
    
    for paper in papers:
        dates = paper.get('dates', {})
        
        # 统计各种日期的可用性
        if 'received' in dates:
            date_stats['received_count'] += 1
        if 'accepted' in dates:
            date_stats['accepted_count'] += 1
        if 'published' in dates or 'pubmed' in dates:
            date_stats['published_count'] += 1
        
        # 计算审稿周期 (received -> accepted)
        if 'received' in dates and 'accepted' in dates:
            days = (dates['accepted'] - dates['received']).days
            if 0 <= days <= 365:  # 合理范围内
                review_cycles.append(days)
        
        # 计算发表周期 (accepted -> published)
        if 'accepted' in dates and ('published' in dates or 'pubmed' in dates):
            pub_date = dates.get('published') or dates.get('pubmed')
            days = (pub_date - dates['accepted']).days
            if 0 <= days <= 365:
                publication_cycles.append(days)
        
        # 计算总周期 (received -> published)
        if 'received' in dates and ('published' in dates or 'pubmed' in dates):
            pub_date = dates.get('published') or dates.get('pubmed')
            days = (pub_date - dates['received']).days
            if 0 <= days <= 730:  # 2年内合理
                total_cycles.append(days)
                date_stats['complete_cycle_count'] += 1
    
    # 计算统计值
    stats = {
        'date_availability': date_stats,
        'review_cycle': calculate_cycle_stats(review_cycles, "审稿周期"),
        'publication_cycle': calculate_cycle_stats(publication_cycles, "发表周期"),
        'total_cycle': calculate_cycle_stats(total_cycles, "总周期")
    }
    
    return stats

def calculate_cycle_stats(cycles: List[int], cycle_name: str) -> Dict[str, Any]:
    """计算周期统计值"""
    if not cycles:
        return {
            'count': 0,
            'mean_days': 0,
            'median_days': 0,
            'min_days': 0,
            'max_days': 0,
            'std_days': 0
        }
    
    return {
        'count': len(cycles),
        'mean_days': round(statistics.mean(cycles), 1),
        'median_days': round(statistics.median(cycles), 1),
        'min_days': min(cycles),
        'max_days': max(cycles),
        'std_days': round(statistics.stdev(cycles) if len(cycles) > 1 else 0, 1)
    }

def print_journal_stats(journal_name: str, stats: Dict[str, Any]):
    """打印期刊统计结果"""
    print(f"   📈 统计结果:")
    print(f"      总文献数: {stats['total_papers']}")
    
    date_avail = stats['date_availability']
    print(f"      日期可用性:")
    print(f"        - 有接收日期: {date_avail['received_count']} 篇")
    print(f"        - 有接受日期: {date_avail['accepted_count']} 篇")
    print(f"        - 有发表日期: {date_avail['published_count']} 篇")
    print(f"        - 完整周期: {date_avail['complete_cycle_count']} 篇")
    
    # 审稿周期
    review = stats['review_cycle']
    if review['count'] > 0:
        print(f"      审稿周期 (接收→接受): {review['count']} 篇样本")
        print(f"        - 平均: {review['mean_days']} 天")
        print(f"        - 中位数: {review['median_days']} 天")
        print(f"        - 范围: {review['min_days']}-{review['max_days']} 天")
    
    # 总周期
    total = stats['total_cycle']
    if total['count'] > 0:
        print(f"      总周期 (接收→发表): {total['count']} 篇样本")
        print(f"        - 平均: {total['mean_days']} 天")
        print(f"        - 中位数: {total['median_days']} 天")

def generate_comprehensive_report(all_stats: Dict[str, Dict[str, Any]]):
    """生成综合报告"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print(f"\n" + "=" * 100)
    print("📊 各期刊审稿周期综合对比")
    print("=" * 100)
    
    # 按审稿周期排序
    journals_with_cycles = []
    for journal, stats in all_stats.items():
        review_cycle = stats['review_cycle']
        if review_cycle['count'] > 0:
            journals_with_cycles.append((journal, review_cycle['mean_days'], stats))
    
    journals_with_cycles.sort(key=lambda x: x[1])  # 按平均审稿周期排序
    
    print(f"{'期刊名称':<35} {'样本数':<8} {'平均审稿周期':<12} {'中位数':<8} {'范围':<15}")
    print("-" * 85)
    
    for journal, mean_days, stats in journals_with_cycles:
        review = stats['review_cycle']
        range_str = f"{review['min_days']}-{review['max_days']}"
        print(f"{journal:<35} {review['count']:<8} {mean_days:<12} {review['median_days']:<8} {range_str:<15}")
    
    # 保存详细报告
    report_data = {
        'analysis_time': datetime.now().isoformat(),
        'summary': {
            'total_journals_analyzed': len(all_stats),
            'journals_with_review_data': len(journals_with_cycles)
        },
        'journal_stats': all_stats
    }
    
    filename = f"journal_review_cycles_{timestamp}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n✅ 详细报告已保存到: {filename}")

def get_text(element) -> str:
    """安全获取元素文本"""
    if element is None:
        return ''
    return ''.join(element.itertext()).strip()

if __name__ == "__main__":
    analyze_journal_review_cycles()
