#!/usr/bin/env python3
"""
优化的期刊审稿周期分析 - 每期刊限制50篇文献
"""

import requests
import xml.etree.ElementTree as ET
import json
import csv
from datetime import datetime
from typing import Dict, List, Any, Optional
import statistics
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OptimizedJournalAnalyzer:
    """优化的期刊分析器 - 每期刊50篇文献样本"""
    
    def __init__(self, max_workers: int = 10, sample_size: int = 50, rate_limit: float = 0.2):
        self.max_workers = max_workers
        self.sample_size = sample_size
        self.rate_limit = rate_limit
        self.progress_lock = threading.Lock()
        self.completed_count = 0
        self.total_journals = 0
        
    def analyze_journals_optimized(self):
        """优化的期刊分析流程"""
        
        print("=" * 100)
        print("优化期刊审稿周期分析 (每期刊50篇文献样本)")
        print("=" * 100)
        
        # 获取期刊列表
        journals_list = self.get_comprehensive_journals_list()
        self.total_journals = len(journals_list)
        
        print(f"期刊总数: {self.total_journals}")
        print(f"每期刊样本: {self.sample_size} 篇文献")
        print(f"并发线程: {self.max_workers}")
        print(f"预计总文献: {self.total_journals * self.sample_size}")
        print("-" * 100)
        
        start_time = time.time()
        successful_results = []
        
        # 并发分析
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_journal = {
                executor.submit(self.analyze_single_journal_optimized, journal): journal 
                for journal in journals_list
            }
            
            for future in as_completed(future_to_journal):
                journal = future_to_journal[future]
                try:
                    result = future.result()
                    if result:
                        successful_results.append(result)
                        self.log_progress(journal, result)
                    else:
                        logger.warning(f"❌ {journal}: 无有效审稿数据")
                        
                except Exception as e:
                    logger.error(f"❌ {journal}: 分析异常 - {e}")
                
                self.update_progress()
        
        end_time = time.time()
        self.print_completion_summary(successful_results, end_time - start_time)
        
        # 保存和报告
        self.save_optimized_results(successful_results)
        self.generate_comprehensive_report(successful_results)
        
        return successful_results

    def analyze_single_journal_optimized(self, journal_name: str) -> Optional[Dict[str, Any]]:
        """优化的单期刊分析 - 限制50篇文献"""
        
        # 添加速率限制
        time.sleep(self.rate_limit)
        
        # 构建检索式 - 近一年文献
        search_query = f'("{journal_name}"[Journal]) AND (("2024/01/01"[Date - Create] : "2025/12/31"[Date - Create]))'
        
        try:
            # 步骤1: 搜索获取PMID (限制50篇)
            pmids = self.search_papers_limited(search_query, self.sample_size)
            if not pmids:
                return None
            
            # 步骤2: 获取详细信息
            papers_with_dates = self.fetch_papers_with_review_dates(pmids)
            if not papers_with_dates:
                return None
            
            # 步骤3: 计算审稿周期
            review_data = self.calculate_comprehensive_review_metrics(papers_with_dates)
            if not review_data['review_cycles']:
                return None
            
            # 步骤4: 构建结果
            result = {
                'journal_name': journal_name,
                'sample_size': len(pmids),
                'papers_analyzed': len(papers_with_dates),
                'papers_with_review_data': len(review_data['review_cycles']),
                'data_completeness_rate': round((len(review_data['review_cycles']) / len(papers_with_dates)) * 100, 1),
                
                # 审稿周期统计
                'avg_review_days': round(statistics.mean(review_data['review_cycles']), 1),
                'median_review_days': round(statistics.median(review_data['review_cycles']), 1),
                'min_review_days': min(review_data['review_cycles']),
                'max_review_days': max(review_data['review_cycles']),
                'std_review_days': round(statistics.stdev(review_data['review_cycles']) if len(review_data['review_cycles']) > 1 else 0, 1),
                
                # 发表周期统计
                'publication_metrics': review_data['publication_metrics'],
                
                # 元数据
                'analysis_thread': threading.current_thread().name,
                'analysis_timestamp': datetime.now().isoformat(),
                'sample_pmids': pmids[:10]  # 保存前10个PMID作为样本
            }
            
            return result
            
        except Exception as e:
            logger.error(f"{journal_name} 分析失败: {e}")
            return None

    def search_papers_limited(self, query: str, limit: int) -> List[str]:
        """搜索文献 - 限制数量"""
        try:
            base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            params = {
                'db': 'pubmed',
                'term': query,
                'retmax': limit,
                'retmode': 'xml',
                'sort': 'relevance',  # 按相关性排序获取最相关的文献
                'tool': 'NNScholar',
                'email': 'test@nnscholar.com'
            }
            
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            pmids = [id_elem.text for id_elem in root.findall('.//Id')]
            
            return pmids[:limit]  # 确保不超过限制
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []

    def fetch_papers_with_review_dates(self, pmids: List[str]) -> List[Dict[str, Any]]:
        """获取包含审稿日期的文献详细信息"""
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
            
            return self.parse_papers_for_review_analysis(response.content)
            
        except Exception as e:
            logger.error(f"获取文献详情失败: {e}")
            return []

    def parse_papers_for_review_analysis(self, xml_content: bytes) -> List[Dict[str, Any]]:
        """解析文献XML - 专注于审稿周期分析"""
        papers = []
        
        try:
            root = ET.fromstring(xml_content)
            
            for article_elem in root.findall('.//PubmedArticle'):
                paper_data = self.extract_comprehensive_dates(article_elem)
                if paper_data:
                    papers.append(paper_data)
                    
        except ET.ParseError as e:
            logger.error(f"XML解析失败: {e}")
        
        return papers

    def extract_comprehensive_dates(self, article_elem) -> Optional[Dict[str, Any]]:
        """提取文献的完整时间信息"""
        try:
            # 基本信息
            medline_citation = article_elem.find('.//MedlineCitation')
            if medline_citation is None:
                return None
            
            pmid = self.get_text(medline_citation.find('.//PMID'))
            if not pmid:
                return None
            
            # 提取所有时间信息
            all_dates = {}
            
            # 从PubmedData/History提取
            pubmed_data = article_elem.find('.//PubmedData')
            if pubmed_data is not None:
                history = pubmed_data.find('.//History')
                if history is not None:
                    for pub_date in history.findall('.//PubMedPubDate'):
                        status = pub_date.get('PubStatus', '')
                        date_obj = self.parse_date_with_precision(pub_date)
                        if date_obj:
                            all_dates[status] = date_obj
                
                # 发表状态
                pub_status = pubmed_data.find('.//PublicationStatus')
                publication_status = self.get_text(pub_status) if pub_status is not None else ''
            
            # 从期刊信息提取发表日期
            article = article_elem.find('.//Article')
            if article is not None:
                journal = article.find('.//Journal')
                if journal is not None:
                    journal_issue = journal.find('.//JournalIssue')
                    if journal_issue is not None:
                        pub_date = journal_issue.find('.//PubDate')
                        if pub_date is not None:
                            journal_date = self.parse_date_with_precision(pub_date)
                            if journal_date:
                                all_dates['journal_published'] = journal_date
            
            # 只返回有足够时间信息的文献
            if len(all_dates) >= 2:
                return {
                    'pmid': pmid,
                    'all_dates': all_dates,
                    'publication_status': publication_status,
                    'has_received': 'received' in all_dates,
                    'has_accepted': 'accepted' in all_dates,
                    'has_published': any(key in all_dates for key in ['pubmed', 'published', 'journal_published'])
                }
            
            return None
            
        except Exception as e:
            logger.error(f"提取日期信息失败: {e}")
            return None

    def parse_date_with_precision(self, date_elem) -> Optional[datetime]:
        """高精度日期解析"""
        try:
            year = self.get_text(date_elem.find('.//Year'))
            month = self.get_text(date_elem.find('.//Month'))
            day = self.get_text(date_elem.find('.//Day'))
            hour = self.get_text(date_elem.find('.//Hour'))
            minute = self.get_text(date_elem.find('.//Minute'))
            
            if not year:
                return None
            
            # 处理月份
            if month:
                try:
                    month_num = int(month)
                except ValueError:
                    month_names = {
                        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                    }
                    month_num = month_names.get(month[:3], 1)
            else:
                month_num = 1
            
            day_num = int(day) if day else 1
            hour_num = int(hour) if hour else 0
            minute_num = int(minute) if minute else 0
            
            return datetime(int(year), month_num, day_num, hour_num, minute_num)
            
        except (ValueError, TypeError):
            return None

    def calculate_comprehensive_review_metrics(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算综合审稿指标"""
        review_cycles = []  # 审稿周期 (received -> accepted)
        publication_delays = []  # 发表延迟 (accepted -> published)
        total_cycles = []  # 总周期 (received -> published)
        
        date_availability = {
            'received_count': 0,
            'accepted_count': 0,
            'published_count': 0,
            'complete_cycle_count': 0
        }
        
        for paper in papers:
            dates = paper.get('all_dates', {})
            
            # 统计日期可用性
            if 'received' in dates:
                date_availability['received_count'] += 1
            if 'accepted' in dates:
                date_availability['accepted_count'] += 1
            if any(key in dates for key in ['pubmed', 'published', 'journal_published']):
                date_availability['published_count'] += 1
            
            # 计算审稿周期 (received -> accepted)
            if 'received' in dates and 'accepted' in dates:
                days = (dates['accepted'] - dates['received']).days
                if 0 <= days <= 730:  # 2年内合理
                    review_cycles.append(days)
            
            # 计算发表延迟 (accepted -> published)
            if 'accepted' in dates:
                pub_date = dates.get('pubmed') or dates.get('published') or dates.get('journal_published')
                if pub_date:
                    days = (pub_date - dates['accepted']).days
                    if 0 <= days <= 365:  # 1年内合理
                        publication_delays.append(days)
            
            # 计算总周期 (received -> published)
            if 'received' in dates:
                pub_date = dates.get('pubmed') or dates.get('published') or dates.get('journal_published')
                if pub_date:
                    days = (pub_date - dates['received']).days
                    if 0 <= days <= 1095:  # 3年内合理
                        total_cycles.append(days)
                        date_availability['complete_cycle_count'] += 1
        
        # 计算发表周期统计
        publication_metrics = {}
        if publication_delays:
            publication_metrics = {
                'avg_publication_delay': round(statistics.mean(publication_delays), 1),
                'median_publication_delay': round(statistics.median(publication_delays), 1),
                'publication_delay_samples': len(publication_delays)
            }
        
        if total_cycles:
            publication_metrics.update({
                'avg_total_cycle': round(statistics.mean(total_cycles), 1),
                'median_total_cycle': round(statistics.median(total_cycles), 1),
                'total_cycle_samples': len(total_cycles)
            })
        
        return {
            'review_cycles': review_cycles,
            'publication_metrics': publication_metrics,
            'date_availability': date_availability
        }

    def get_comprehensive_journals_list(self) -> List[str]:
        """获取综合期刊列表"""
        return [
            # 顶级综合期刊
            "Nature", "Science", "Cell", "PNAS",
            
            # Nature系列
            "Nature Medicine", "Nature Biotechnology", "Nature Genetics",
            "Nature Immunology", "Nature Neuroscience", "Nature Cell Biology",
            "Nature Communications", "Nature Methods", "Nature Structural & Molecular Biology",
            "Nature Chemical Biology", "Nature Reviews Molecular Cell Biology",
            "Nature Reviews Drug Discovery", "Nature Reviews Cancer",
            "Nature Reviews Immunology", "Nature Reviews Genetics",
            
            # Cell系列
            "Cell Metabolism", "Cell Stem Cell", "Cancer Cell",
            "Molecular Cell", "Developmental Cell", "Current Biology",
            "Cell Reports", "Cell Host & Microbe", "Cell Chemical Biology",
            
            # 医学期刊
            "The Lancet", "New England Journal of Medicine", "JAMA",
            "BMJ", "Annals of Internal Medicine", "The Lancet Oncology",
            "The Lancet Neurology", "Blood", "Circulation",
            
            # 生物医学期刊
            "eLife", "EMBO Journal", "EMBO Reports", "PLoS Biology",
            "Journal of Clinical Investigation", "Immunity", "Neuron",
            "Cancer Research", "Journal of Experimental Medicine",
            "Genes & Development", "Molecular Biology of the Cell",
            
            # 生物信息学和基因组学
            "Genome Research", "Genome Biology", "Nucleic Acids Research",
            "Bioinformatics", "Nature Genetics", "Genome Medicine",
            
            # 其他重要期刊
            "Science Translational Medicine", "Science Immunology",
            "Proceedings of the Royal Society B", "Journal of Cell Biology",
            "Plant Cell", "Development", "EMBO Molecular Medicine"
        ]

    def log_progress(self, journal: str, result: Dict[str, Any]):
        """记录进度"""
        logger.info(f"✅ {journal}: 审稿周期 {result['avg_review_days']:.1f}天 "
                   f"(样本: {result['papers_with_review_data']}/{result['sample_size']})")

    def update_progress(self):
        """更新进度显示"""
        with self.progress_lock:
            self.completed_count += 1
            progress = (self.completed_count / self.total_journals) * 100
            print(f"\r进度: {self.completed_count}/{self.total_journals} ({progress:.1f}%)", end="", flush=True)

    def print_completion_summary(self, results: List[Dict[str, Any]], elapsed_time: float):
        """打印完成摘要"""
        print()  # 换行
        print(f"\n" + "=" * 100)
        print(f"🎉 优化分析完成！")
        print(f"成功分析: {len(results)}/{self.total_journals} 个期刊")
        print(f"总耗时: {elapsed_time:.1f} 秒")
        print(f"平均每期刊: {elapsed_time / self.total_journals:.1f} 秒")
        print(f"总文献分析: {sum(r['papers_analyzed'] for r in results)} 篇")
        print("=" * 100)

    def save_optimized_results(self, results: List[Dict[str, Any]]):
        """保存优化分析结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # JSON格式 - 详细数据
        json_filename = f"optimized_journal_analysis_{timestamp}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump({
                'analysis_method': 'optimized_sampling',
                'sample_size_per_journal': self.sample_size,
                'max_workers': self.max_workers,
                'analysis_time': datetime.now().isoformat(),
                'total_journals_analyzed': len(results),
                'total_papers_analyzed': sum(r['papers_analyzed'] for r in results),
                'results': results
            }, f, ensure_ascii=False, indent=2, default=str)
        
        # CSV格式 - 汇总数据
        csv_filename = f"optimized_journal_analysis_{timestamp}.csv"
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                '期刊名称', '样本大小', '分析文献数', '有审稿数据', '数据完整率(%)',
                '平均审稿周期(天)', '中位数(天)', '最短(天)', '最长(天)', '标准差(天)',
                '平均发表延迟(天)', '平均总周期(天)', '分析线程'
            ])
            
            for result in results:
                pub_metrics = result.get('publication_metrics', {})
                writer.writerow([
                    result['journal_name'], result['sample_size'], result['papers_analyzed'],
                    result['papers_with_review_data'], result['data_completeness_rate'],
                    result['avg_review_days'], result['median_review_days'],
                    result['min_review_days'], result['max_review_days'], result['std_review_days'],
                    pub_metrics.get('avg_publication_delay', 'N/A'),
                    pub_metrics.get('avg_total_cycle', 'N/A'),
                    result['analysis_thread']
                ])
        
        print(f"\n✅ 优化分析结果已保存:")
        print(f"   详细数据 (JSON): {json_filename}")
        print(f"   汇总数据 (CSV): {csv_filename}")

    def generate_comprehensive_report(self, results: List[Dict[str, Any]]):
        """生成综合分析报告"""
        if not results:
            return
        
        # 按平均审稿周期排序
        sorted_results = sorted(results, key=lambda x: x['avg_review_days'])
        
        print(f"\n📊 期刊审稿周期排行榜 (基于50篇文献样本)")
        print("=" * 130)
        print(f"{'排名':<4} {'期刊名称':<40} {'审稿周期':<10} {'中位数':<8} {'样本':<6} {'完整率':<8} {'发表延迟':<10}")
        print("-" * 130)
        
        for i, result in enumerate(sorted_results, 1):
            pub_delay = result.get('publication_metrics', {}).get('avg_publication_delay', 'N/A')
            pub_delay_str = f"{pub_delay:.1f}" if isinstance(pub_delay, (int, float)) else str(pub_delay)
            
            print(f"{i:<4} {result['journal_name']:<40} {result['avg_review_days']:<10.1f} "
                  f"{result['median_review_days']:<8.1f} {result['papers_with_review_data']:<6} "
                  f"{result['data_completeness_rate']:<8.1f}% {pub_delay_str:<10}")
        
        # 统计摘要
        avg_cycles = [r['avg_review_days'] for r in results]
        total_papers = sum(r['papers_analyzed'] for r in results)
        total_with_data = sum(r['papers_with_review_data'] for r in results)
        
        print(f"\n📈 分析摘要:")
        print(f"   成功分析期刊: {len(results)}")
        print(f"   总分析文献: {total_papers} 篇")
        print(f"   有效审稿数据: {total_with_data} 篇 ({total_with_data/total_papers*100:.1f}%)")
        print(f"   平均审稿周期: {statistics.mean(avg_cycles):.1f} 天")
        print(f"   中位数审稿周期: {statistics.median(avg_cycles):.1f} 天")
        print(f"   最快期刊: {sorted_results[0]['journal_name']} ({sorted_results[0]['avg_review_days']:.1f}天)")
        print(f"   最慢期刊: {sorted_results[-1]['journal_name']} ({sorted_results[-1]['avg_review_days']:.1f}天)")

    def get_text(self, element) -> str:
        """安全获取元素文本"""
        if element is None:
            return ''
        return ''.join(element.itertext()).strip()

def main():
    """主函数"""
    analyzer = OptimizedJournalAnalyzer(
        max_workers=10,      # 10个并发线程
        sample_size=50,      # 每期刊50篇文献
        rate_limit=0.2       # 每请求0.2秒间隔
    )
    
    results = analyzer.analyze_journals_optimized()
    print(f"\n🎉 分析完成！共分析 {len(results)} 个期刊")

if __name__ == "__main__":
    main()
