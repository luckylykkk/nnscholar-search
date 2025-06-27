#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
文献摘要和创新点分析模块

此模块提供了生成文献摘要和创新点分析的功能，可以作为独立脚本运行，
也可以被主应用程序导入使用。
"""

import os
import json
import requests
import logging
import re
import time
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('paper_insights.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 加载环境变量
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    logger.info(f"加载环境变量文件: {env_path}")
    load_dotenv(env_path, verbose=True, override=True)
else:
    logger.warning(f"未找到.env文件: {env_path}，将使用系统环境变量")

def call_deepseek_api(prompt):
    """
    调用DeepSeek API生成文本
    
    Args:
        prompt (str): 提示词
        
    Returns:
        dict: API响应
    """
    api_url = os.getenv('DEEPSEEK_API_URL', 'https://api.siliconflow.cn/v1/chat/completions')
    api_key = os.getenv('DEEPSEEK_API_KEY')
    model = os.getenv('DEEPSEEK_MODEL', 'deepseek-ai/DeepSeek-V2.5')
    
    if not api_key:
        raise ValueError("未设置DEEPSEEK_API_KEY环境变量")
    
    logger.info(f"使用模型: {model}")
    logger.info(f"API URL: {api_url}")
    logger.info(f"提示词长度: {len(prompt)}")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    try:
        logger.info("发送API请求...")
        response = requests.post(api_url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()
        logger.info("API请求成功")
        return result
    except Exception as e:
        logger.error(f"API请求失败: {str(e)}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"响应状态码: {e.response.status_code}")
            logger.error(f"响应内容: {e.response.text}")
        raise

def generate_paper_insights(paper, query):
    """
    为单篇文献生成摘要和创新点分析
    
    Args:
        paper (dict): 文献信息
        query (str): 查询字符串
        
    Returns:
        tuple: (摘要, 创新点分析)
    """
    title = paper.get('title', '')
    authors = ', '.join(paper.get('authors', []))
    year = paper.get('pub_year', '')
    keywords = ', '.join(paper.get('keywords', []))
    abstract = paper.get('abstract', '')
    paper_id = paper.get('pmid', '')
    
    logger.info(f"生成文献洞察 (ID: {paper_id})")
    logger.info(f"标题: {title}")
    
    prompt = f"""
    请分析以下学术文献，并用中文提供简明的总结摘要和创新点分析：
    
    标题: {title}
    作者: {authors}
    发表年份: {year}
    关键词: {keywords}
    摘要: {abstract}
    用户查询: {query}
    
    请以JSON格式返回以下内容:
    {{
        "summary": "对文章内容的简明总结，100字以内，必须使用中文",
        "innovation": "文章的主要创新点和贡献，100字以内，必须使用中文"
    }}
    """
    
    try:
        response = call_deepseek_api(prompt)
        
        if response and 'choices' in response:
            content = response['choices'][0]['message']['content']
            logger.info(f"API响应内容前100字符: {content[:100]}...")
            
            # 预处理内容，移除可能的代码块标记
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            
            # 尝试解析JSON
            try:
                result = json.loads(content)
                summary = result.get('summary', '未能生成摘要')
                innovation = result.get('innovation', '未能生成创新点分析')
                
                # 限制字数
                if len(summary) > 100:
                    summary = summary[:97] + '...'
                if len(innovation) > 100:
                    innovation = innovation[:97] + '...'
                
                logger.info(f"成功解析JSON")
                logger.info(f"摘要: {summary}")
                logger.info(f"创新点: {innovation}")
                
                return summary, innovation
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {str(e)}")
                
                # 使用正则表达式提取
                summary_match = re.search(r'"summary"\s*:\s*"([^"]+)"', content)
                innovation_match = re.search(r'"innovation"\s*:\s*"([^"]+)"', content)
                
                if summary_match or innovation_match:
                    summary = summary_match.group(1) if summary_match else '未能解析摘要'
                    innovation = innovation_match.group(1) if innovation_match else '未能解析创新点分析'
                    
                    # 限制字数
                    if len(summary) > 100:
                        summary = summary[:97] + '...'
                    if len(innovation) > 100:
                        innovation = innovation[:97] + '...'
                    
                    logger.info(f"使用正则表达式提取")
                    logger.info(f"摘要: {summary}")
                    logger.info(f"创新点: {innovation}")
                    
                    return summary, innovation
                else:
                    # 如果正则表达式也失败，尝试直接提取内容
                    logger.info("正则表达式提取失败，尝试直接提取内容")
                    
                    # 查找"summary"和"innovation"关键词
                    summary_pos = content.find("summary")
                    innovation_pos = content.find("innovation")
                    
                    if summary_pos > 0 and innovation_pos > 0:
                        # 提取两个关键词之间的内容作为摘要
                        summary_start = content.find(":", summary_pos) + 1
                        summary_end = innovation_pos
                        if summary_start > 0 and summary_end > summary_start:
                            summary = content[summary_start:summary_end].strip().strip('",:')
                        
                        # 提取innovation后面的内容作为创新点
                        innovation_start = content.find(":", innovation_pos) + 1
                        if innovation_start > 0:
                            innovation = content[innovation_start:].strip().strip('",:}')
                        
                        # 限制字数
                        if len(summary) > 100:
                            summary = summary[:97] + '...'
                        if len(innovation) > 100:
                            innovation = innovation[:97] + '...'
                        
                        logger.info(f"直接提取内容")
                        logger.info(f"摘要: {summary}")
                        logger.info(f"创新点: {innovation}")
                        return summary, innovation
        
        logger.warning("API响应无效或为空")
        return '未能生成摘要', '未能生成创新点分析'
    except Exception as e:
        logger.error(f"生成文献洞察时出错: {str(e)}")
        return '生成过程出错', '生成过程出错'

def generate_batch_paper_insights(papers, query, batch_size=2, min_relevance=50):
    """
    批量生成多篇文献的摘要和创新点分析
    
    Args:
        papers (list): 文献列表
        query (str): 查询字符串
        batch_size (int): 批量大小
        min_relevance (float): 最低相关度阈值
        
    Returns:
        dict: 文献ID到(摘要,创新点)的映射
    """
    results = {}
    
    # 筛选相关度高的文献
    relevant_papers = []
    logger.info(f"开始筛选相关度高的文献，总文献数: {len(papers)}")
    
    for paper in papers:
        paper_id = paper.get('pmid', '')
        if not paper_id:
            paper_id = str(hash(paper.get('title', '')))  # 使用标题哈希作为备用ID
            logger.warning(f"文献没有PMID，使用标题哈希作为ID: {paper_id}")
        
        # 检查是否已有相关度分数
        if 'relevance_score' in paper:
            relevance_score = paper['relevance_score']
            logger.info(f"使用预计算的相关度分数: {relevance_score} (ID: {paper_id})")
        else:
            # 如果没有相关度分数，默认为100（确保处理）
            relevance_score = 100
            logger.info(f"未找到相关度分数，默认设为100 (ID: {paper_id})")
        
        # 设置相关度阈值
        if relevance_score >= min_relevance:
            paper['relevance_score'] = relevance_score
            relevant_papers.append(paper)
            logger.info(f"文献相关度 {relevance_score} >= {min_relevance}，添加到处理列表 (ID: {paper_id})")
        else:
            logger.info(f"文献相关度 {relevance_score} < {min_relevance}，不处理 (ID: {paper_id})")
    
    # 按相关度排序
    relevant_papers.sort(key=lambda p: p.get('relevance_score', 0), reverse=True)
    logger.info(f"按相关度排序后，待处理文献数: {len(relevant_papers)}")
    
    # 限制处理数量，最多处理前15篇最相关的文献
    relevant_papers = relevant_papers[:15]
    logger.info(f"限制处理数量后，实际处理文献数: {len(relevant_papers)}")
    
    # 如果没有相关文献，返回空结果
    if not relevant_papers:
        logger.warning("没有找到相关度足够高的文献，跳过生成摘要和创新点分析")
        return results
    
    # 分批处理
    for i in range(0, len(relevant_papers), batch_size):
        batch = relevant_papers[i:i+batch_size]
        logger.info(f"处理批次 {i//batch_size + 1}/{(len(relevant_papers)-1)//batch_size + 1}，文献数: {len(batch)}")
        
        # 构建批量提示词
        prompt = "请分析以下多篇学术文献，并用中文提供每篇文献的简明总结摘要和创新点分析。\n\n"
        
        # 记录批次中的文献ID，用于后续匹配
        batch_paper_ids = []
        
        for idx, paper in enumerate(batch):
            title = paper.get('title', '')
            authors = ', '.join(paper.get('authors', []))
            year = paper.get('pub_year', '')
            keywords = ', '.join(paper.get('keywords', []))
            abstract = paper.get('abstract', '')
            paper_id = paper.get('pmid', '')
            if not paper_id:
                paper_id = str(hash(title))
            
            batch_paper_ids.append(paper_id)
            
            prompt += f"""
            文献{idx+1} ID:{paper_id}
            标题: {title}
            作者: {authors}
            发表年份: {year}
            关键词: {keywords}
            摘要: {abstract}
            
            """
        
        prompt += f"""
        用户查询: {query}
        
        请以JSON格式返回分析结果，每篇文献包含总结摘要和创新点分析：
        {{
            "papers": [
                {{
                    "id": "文献ID",
                    "summary": "对文章内容的简明总结，100字以内，必须使用中文",
                    "innovation": "文章的主要创新点和贡献，100字以内，必须使用中文"
                }},
                ...
            ]
        }}
        """
        
        try:
            # 调用DeepSeek API
            response = call_deepseek_api(prompt)
            
            if response and 'choices' in response:
                content = response['choices'][0]['message']['content']
                logger.info(f"API响应内容前100字符: {content[:100]}...")
                
                # 保存完整响应到文件，便于调试
                try:
                    # 预处理内容，移除可能的代码块标记
                    clean_content = re.sub(r'^```json\s*', '', content)
                    clean_content = re.sub(r'\s*```$', '', clean_content)
                    clean_content = clean_content.strip()
                    
                    # 临时文件路径
                    temp_file_path = f"batch_response_{i}.json"
                    temp_txt_path = f"batch_response_{i}.txt"
                    
                    # 尝试解析为JSON对象
                    try:
                        json_obj = json.loads(clean_content)
                        
                        # 只在调试模式下保存JSON文件
                        debug_mode = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
                        if debug_mode:
                            with open(temp_file_path, "w", encoding="utf-8") as f:
                                json.dump(json_obj, f, ensure_ascii=False, indent=2)
                            logger.info(f"调试模式：已保存格式化的JSON响应到文件: {temp_file_path}")
                    except json.JSONDecodeError as e:
                        # 如果不是有效的JSON，只在调试模式下保存为文本文件
                        logger.warning(f"响应不是有效的JSON: {str(e)}")
                        debug_mode = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
                        if debug_mode:
                            with open(temp_txt_path, "w", encoding="utf-8") as f:
                                f.write(content)
                            logger.info(f"调试模式：已保存原始响应到文件: {temp_txt_path}")
                except Exception as e:
                    logger.error(f"处理响应内容失败: {str(e)}")
                
                # 预处理内容，移除可能的代码块标记
                content = re.sub(r'^```json\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                
                # 尝试解析JSON
                try:
                    result = json.loads(content)
                    papers_results = result.get('papers', [])
                    
                    for paper_result in papers_results:
                        paper_id = paper_result.get('id')
                        if paper_id:
                            summary = paper_result.get('summary', '未能生成摘要')
                            innovation = paper_result.get('innovation', '未能生成创新点分析')
                            
                            # 限制字数
                            if len(summary) > 100:
                                summary = summary[:97] + '...'
                            if len(innovation) > 100:
                                innovation = innovation[:97] + '...'
                            
                            logger.info(f"文献 ID: {paper_id}")
                            logger.info(f"摘要: {summary}")
                            logger.info(f"创新点: {innovation}")
                            
                            results[paper_id] = (summary, innovation)
                        else:
                            logger.warning(f"解析的结果中缺少id字段: {paper_result}")
                            
                            # 尝试通过索引匹配
                            idx = papers_results.index(paper_result)
                            if idx < len(batch_paper_ids):
                                paper_id = batch_paper_ids[idx]
                                summary = paper_result.get('summary', '未能生成摘要')
                                innovation = paper_result.get('innovation', '未能生成创新点分析')
                                
                                # 限制字数
                                if len(summary) > 100:
                                    summary = summary[:97] + '...'
                                if len(innovation) > 100:
                                    innovation = innovation[:97] + '...'
                                
                                logger.info(f"通过索引匹配 ID: {paper_id}")
                                logger.info(f"摘要: {summary}")
                                logger.info(f"创新点: {innovation}")
                                
                                results[paper_id] = (summary, innovation)
                        
                        # 删除可能存在的临时文件
                        temp_file_path = f"batch_response_{i}.json"
                        temp_txt_path = f"batch_response_{i}.txt"
                        
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)
                            logger.info(f"已删除临时JSON文件: {temp_file_path}")
                            
                        if os.path.exists(temp_txt_path):
                            os.remove(temp_txt_path)
                            logger.info(f"已删除临时文本文件: {temp_txt_path}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {str(e)}")
                    
                    # 尝试为每篇文献单独生成
                    for paper in batch:
                        paper_id = paper.get('pmid', '')
                        if not paper_id:
                            paper_id = str(hash(paper.get('title', '')))
                        summary, innovation = generate_paper_insights(paper, query)
                        results[paper_id] = (summary, innovation)
        except Exception as e:
            logger.error(f"批量生成文献洞察时出错: {str(e)}")
            
            # 尝试为每篇文献单独生成
            for paper in batch:
                paper_id = paper.get('pmid', '')
                if not paper_id:
                    paper_id = str(hash(paper.get('title', '')))
                summary, innovation = generate_paper_insights(paper, query)
                results[paper_id] = (summary, innovation)
    
    logger.info(f"批量生成完成，共生成{len(results)}篇文献的摘要和创新点分析")
    return results

def process_papers(papers, query, min_relevance=50, batch_size=2):
    """
    处理文献列表，生成摘要和创新点分析
    
    Args:
        papers (list): 文献列表
        query (str): 查询字符串
        min_relevance (float): 最低相关度阈值
        batch_size (int): 批量大小
        
    Returns:
        dict: 文献ID到(摘要,创新点)的映射
    """
    logger.info(f"开始处理{len(papers)}篇文献")
    
    # 生成摘要和创新点
    results = generate_batch_paper_insights(papers, query, batch_size, min_relevance)
    
    # 输出结果统计
    logger.info(f"处理完成，共生成{len(results)}篇文献的摘要和创新点分析")
    
    return results

def main():
    """主函数，用于独立运行时测试"""
    # 测试数据
    test_papers = [
        {
            "pmid": "12345678",
            "title": "Aspirin and clinical outcomes in individuals with incidentally diagnosed coronary artery stenosis.",
            "authors": ["Smith J", "Johnson A", "Williams B"],
            "pub_year": "2022",
            "keywords": ["aspirin", "coronary artery stenosis", "cardiovascular outcomes"],
            "abstract": "The widespread use of coronary computed tomographic angiography (CCTA) has increased the number of cases of coronary stenosis in asymptomatic individuals. In this population, we aimed to analyze the net benefit of aspirin, which is currently recommended for secondary cardiovascular prevention."
        },
        {
            "pmid": "87654321",
            "title": "Recent Advances in Deep Learning for Medical Image Analysis",
            "authors": ["Chen X", "Zhang Y", "Li Z"],
            "pub_year": "2023",
            "keywords": ["deep learning", "medical imaging", "artificial intelligence"],
            "abstract": "Deep learning has revolutionized medical image analysis in recent years. This paper reviews the latest advances in deep learning techniques applied to medical imaging, including convolutional neural networks, transformers, and self-supervised learning approaches."
        }
    ]
    
    # 测试查询
    test_query = "心脏磁共振成像技术在心肌梗死中的应用"
    
    # 处理文献
    results = process_papers(test_papers, test_query)
    
    # 打印结果
    print("\n处理结果:")
    for paper_id, (summary, innovation) in results.items():
        paper_title = next((p['title'] for p in test_papers if p['pmid'] == paper_id), "未知标题")
        print(f"\n文献ID: {paper_id}")
        print(f"标题: {paper_title}")
        print(f"摘要: {summary}")
        print(f"创新点: {innovation}")

if __name__ == "__main__":
    main() 