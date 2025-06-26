"""
简化的数据库测试脚本
快速验证各个数据库的基本连接和数据返回格式
"""

import requests
import json
import time
from typing import Dict, Any
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def create_session():
    """创建带有重试机制的会话"""
    session = requests.Session()

    # 设置重试策略
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # 设置请求头
    session.headers.update({
        'User-Agent': 'NNScholar/1.0 (Academic Research Tool)',
        'Accept': 'application/json',
        'Connection': 'keep-alive'
    })

    return session

def test_openalex(query: str = "machine learning", max_results: int = 3) -> Dict[str, Any]:
    """测试OpenAlex API"""
    print("测试 OpenAlex...")

    try:
        session = create_session()
        url = "https://api.openalex.org/works"
        params = {
            'search': query,
            'per-page': max_results,
            'select': 'id,title,display_name,publication_year,authorships,abstract_inverted_index'
        }

        response = session.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        results = data.get('results', [])
        
        print(f"✅ OpenAlex 成功: 找到 {len(results)} 篇文献")
        
        if results:
            sample = results[0]
            print(f"   示例标题: {sample.get('display_name', 'N/A')}")
            print(f"   字段: {list(sample.keys())}")
        
        return {
            'success': True,
            'count': len(results),
            'sample_data': results[0] if results else None,
            'total_results': data.get('meta', {}).get('count', 0)
        }
        
    except Exception as e:
        print(f"❌ OpenAlex 失败: {e}")
        return {'success': False, 'error': str(e)}

def test_arxiv(query: str = "machine learning", max_results: int = 3) -> Dict[str, Any]:
    """测试arXiv API"""
    print("测试 arXiv...")

    try:
        session = create_session()
        # 使用HTTPS而不是HTTP
        url = "https://export.arxiv.org/api/query"
        params = {
            'search_query': f'all:{query}',
            'start': 0,
            'max_results': max_results
        }

        response = session.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        # arXiv返回XML格式
        content = response.content.decode('utf-8')
        
        # 简单计算条目数量
        entry_count = content.count('<entry>')
        
        print(f"✅ arXiv 成功: 找到 {entry_count} 篇文献")
        print(f"   返回格式: XML")
        
        return {
            'success': True,
            'count': entry_count,
            'format': 'XML',
            'sample_content': content[:200] + '...' if len(content) > 200 else content
        }
        
    except Exception as e:
        print(f"❌ arXiv 失败: {e}")
        return {'success': False, 'error': str(e)}

def test_semantic_scholar(query: str = "machine learning", max_results: int = 3) -> Dict[str, Any]:
    """测试Semantic Scholar API"""
    print("测试 Semantic Scholar...")

    try:
        session = create_session()
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {
            'query': query,
            'limit': max_results,
            'fields': 'paperId,title,abstract,year,authors'
        }

        response = session.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        results = data.get('data', [])
        
        print(f"✅ Semantic Scholar 成功: 找到 {len(results)} 篇文献")
        
        if results:
            sample = results[0]
            print(f"   示例标题: {sample.get('title', 'N/A')}")
            print(f"   字段: {list(sample.keys())}")
        
        return {
            'success': True,
            'count': len(results),
            'sample_data': results[0] if results else None,
            'total_results': data.get('total', 0)
        }
        
    except Exception as e:
        print(f"❌ Semantic Scholar 失败: {e}")
        return {'success': False, 'error': str(e)}

def test_doaj(query: str = "machine learning", max_results: int = 3) -> Dict[str, Any]:
    """测试DOAJ API"""
    print("测试 DOAJ...")
    
    try:
        url = "https://doaj.org/api/v2/search/articles"
        params = {
            'q': query,
            'pageSize': max_results
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        results = data.get('results', [])
        
        print(f"✅ DOAJ 成功: 找到 {len(results)} 篇文献")
        
        if results:
            sample = results[0]
            bibjson = sample.get('bibjson', {})
            print(f"   示例标题: {bibjson.get('title', 'N/A')}")
            print(f"   字段: {list(sample.keys())}")
        
        return {
            'success': True,
            'count': len(results),
            'sample_data': results[0] if results else None,
            'total_results': data.get('total', 0)
        }
        
    except Exception as e:
        print(f"❌ DOAJ 失败: {e}")
        return {'success': False, 'error': str(e)}

def test_crossref(query: str = "machine learning", max_results: int = 3) -> Dict[str, Any]:
    """测试Crossref API"""
    print("测试 Crossref...")
    
    try:
        url = "https://api.crossref.org/works"
        params = {
            'query': query,
            'rows': max_results
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        message = data.get('message', {})
        results = message.get('items', [])
        
        print(f"✅ Crossref 成功: 找到 {len(results)} 篇文献")
        
        if results:
            sample = results[0]
            title = sample.get('title', ['N/A'])[0] if sample.get('title') else 'N/A'
            print(f"   示例标题: {title}")
            print(f"   字段: {list(sample.keys())}")
        
        return {
            'success': True,
            'count': len(results),
            'sample_data': results[0] if results else None,
            'total_results': message.get('total-results', 0)
        }
        
    except Exception as e:
        print(f"❌ Crossref 失败: {e}")
        return {'success': False, 'error': str(e)}

def compare_data_formats(results: Dict[str, Dict]) -> None:
    """比较不同数据库的数据格式"""
    print("\n" + "=" * 60)
    print("数据格式对比分析")
    print("=" * 60)
    
    for db_name, result in results.items():
        if result['success'] and result.get('sample_data'):
            print(f"\n{db_name.upper()} 数据格式:")
            sample = result['sample_data']
            
            if db_name == 'doaj':
                # DOAJ的数据在bibjson字段中
                sample = sample.get('bibjson', {})
            
            # 显示主要字段
            title_field = None
            author_field = None
            abstract_field = None
            
            for key in sample.keys():
                if 'title' in key.lower():
                    title_field = key
                elif 'author' in key.lower():
                    author_field = key
                elif 'abstract' in key.lower():
                    abstract_field = key
            
            print(f"  标题字段: {title_field}")
            print(f"  作者字段: {author_field}")
            print(f"  摘要字段: {abstract_field}")
            print(f"  总字段数: {len(sample.keys())}")
            print(f"  所有字段: {list(sample.keys())[:10]}...")  # 只显示前10个字段

def main():
    """主测试函数"""
    print("=" * 60)
    print("多数据库连接测试")
    print("=" * 60)
    
    # 测试所有数据库
    databases = {
        'openalex': test_openalex,
        'arxiv': test_arxiv,
        'semantic_scholar': test_semantic_scholar,
        'doaj': test_doaj,
        'crossref': test_crossref
    }
    
    results = {}
    
    for db_name, test_func in databases.items():
        try:
            result = test_func()
            results[db_name] = result
            time.sleep(1)  # 避免请求过快
        except Exception as e:
            print(f"❌ {db_name} 测试异常: {e}")
            results[db_name] = {'success': False, 'error': str(e)}
    
    # 统计结果
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    successful_dbs = [db for db, result in results.items() if result['success']]
    failed_dbs = [db for db, result in results.items() if not result['success']]
    
    print(f"✅ 成功连接的数据库 ({len(successful_dbs)}/5): {', '.join(successful_dbs)}")
    if failed_dbs:
        print(f"❌ 连接失败的数据库 ({len(failed_dbs)}/5): {', '.join(failed_dbs)}")
    
    # 比较数据格式
    compare_data_formats(results)
    
    # 保存结果
    with open('simple_test_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细结果已保存到: simple_test_results.json")
    
    return len(successful_dbs) >= 3  # 至少3个数据库成功才算测试通过

if __name__ == "__main__":
    success = main()
    print(f"\n测试{'通过' if success else '失败'}!")
    exit(0 if success else 1)
