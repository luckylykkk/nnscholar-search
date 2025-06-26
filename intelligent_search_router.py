"""
智能搜索路由模块
根据用户输入智能选择数据库并转换为对应的检索式
"""

import logging
import re
from typing import List, Dict, Tuple
from app import call_deepseek_api

logger = logging.getLogger(__name__)

class IntelligentSearchRouter:
    """智能搜索路由器"""
    
    def __init__(self):
        # 数据库特征关键词
        self.database_keywords = {
            'pubmed': {
                'keywords': ['医学', '临床', '疾病', '治疗', '药物', '患者', '医院', '诊断', '手术', '癌症', '糖尿病', '心血管', '生物医学', '病理', '药理', '医疗', '健康', 'medical', 'clinical', 'disease', 'treatment', 'drug', 'patient', 'hospital', 'diagnosis', 'surgery', 'cancer', 'diabetes', 'cardiovascular', 'biomedical', 'pathology', 'pharmacology', 'healthcare', 'health'],
                'priority': 1,
                'description': '生物医学和医学文献数据库'
            },
            'arxiv': {
                'keywords': ['物理', '数学', '计算机科学', '人工智能', '机器学习', '深度学习', '算法', '神经网络', '量子', '统计', '概率', '几何', '代数', '微积分', 'physics', 'mathematics', 'computer science', 'artificial intelligence', 'machine learning', 'deep learning', 'algorithm', 'neural network', 'quantum', 'statistics', 'probability', 'geometry', 'algebra', 'calculus'],
                'priority': 2,
                'description': '物理学、数学、计算机科学等预印本论文'
            },
            'semantic_scholar': {
                'keywords': ['计算机', '软件', '编程', '数据科学', '信息技术', '网络', '系统', '数据库', '软件工程', '计算', 'computer', 'software', 'programming', 'data science', 'information technology', 'network', 'system', 'database', 'software engineering', 'computing'],
                'priority': 3,
                'description': 'AI驱动的学术搜索，适合计算机科学和跨学科研究'
            },
            'openalex': {
                'keywords': ['跨学科', '综合', '全领域', '多学科', 'interdisciplinary', 'comprehensive', 'multidisciplinary', 'general'],
                'priority': 4,
                'description': '全学科综合数据库，适合跨领域研究'
            },
            'doaj': {
                'keywords': ['开放获取', '免费', '公开', 'open access', 'free', 'public'],
                'priority': 5,
                'description': '开放获取期刊，适合需要免费全文的研究'
            }
        }
        
        # 学科领域映射
        self.field_mapping = {
            '医学': ['pubmed', 'openalex'],
            '生物学': ['pubmed', 'arxiv', 'openalex'],
            '物理学': ['arxiv', 'openalex'],
            '数学': ['arxiv', 'openalex'],
            '计算机科学': ['arxiv', 'semantic_scholar', 'openalex'],
            '化学': ['openalex', 'semantic_scholar'],
            '工程学': ['openalex', 'semantic_scholar'],
            '社会科学': ['openalex', 'doaj'],
            '人文学科': ['openalex', 'doaj'],
            '环境科学': ['openalex', 'doaj'],
            '教育学': ['openalex', 'doaj']
        }
    
    def analyze_query_and_select_database(self, user_input: str) -> Tuple[str, str, Dict]:
        """
        分析用户输入并选择最适合的数据库

        Returns:
            (recommended_database, detected_field, analysis_result)
        """
        try:
            logger.info(f"分析用户输入: {user_input}")
            
            # 使用DeepSeek分析用户输入
            analysis_prompt = f"""
作为学术搜索专家，请分析以下用户输入的研究内容，并从指定的数据库列表中推荐最适合的单个学术数据库。

用户输入："{user_input}"

**重要：必须从以下5个数据库中选择一个，不能推荐其他数据库：**

1. PubMed - 生物医学和医学文献数据库，适合医学、临床、生物医学研究
2. arXiv - 物理学、数学、计算机科学等预印本论文，适合理工科前沿研究
3. Semantic Scholar - AI驱动的学术搜索，适合计算机科学和跨学科研究
4. OpenAlex - 全学科综合数据库，适合跨领域和综合性研究
5. DOAJ - 开放获取期刊，适合需要免费全文的研究

**选择规则：**
- 医学、临床、生物医学相关 → 选择 PubMed
- 物理学、数学、计算机科学理论 → 选择 arXiv
- 计算机科学应用、AI、机器学习 → 选择 Semantic Scholar
- 跨学科、综合性、社会科学 → 选择 OpenAlex
- 需要开放获取全文 → 选择 DOAJ

请严格按照以下格式输出：

**研究领域识别：** [识别的主要研究领域]
**最佳数据库：** [必须从上述5个数据库中选择一个，只写数据库名称：PubMed/arXiv/Semantic Scholar/OpenAlex/DOAJ]
**推荐理由：** [详细说明为什么这个数据库最适合]
**检索重点：** [指出检索的关键概念和重点]

注意：最佳数据库字段必须严格使用以上5个数据库名称之一，不能使用其他名称或组合。
"""
            
            analysis_result = call_deepseek_api(analysis_prompt)
            logger.info(f"DeepSeek分析结果: {analysis_result}")
            
            # 解析分析结果
            detected_field = self._extract_field_from_analysis(analysis_result)
            recommended_database = self._extract_single_database_from_analysis(analysis_result)

            # 如果DeepSeek分析失败，使用关键词匹配作为备选
            if not recommended_database:
                recommended_database = self._keyword_based_single_selection(user_input)
                detected_field = self._detect_field_by_keywords(user_input)

            analysis_info = {
                'analysis_text': analysis_result,
                'detected_field': detected_field,
                'selection_method': 'ai_analysis' if recommended_database else 'keyword_matching'
            }

            logger.info(f"推荐数据库: {recommended_database}, 检测领域: {detected_field}")

            return recommended_database, detected_field, analysis_info
            
        except Exception as e:
            logger.error(f"分析用户输入时出错: {e}")
            # 回退到关键词匹配
            recommended_database = self._keyword_based_single_selection(user_input)
            detected_field = self._detect_field_by_keywords(user_input)

            return recommended_database, detected_field, {'error': str(e), 'selection_method': 'fallback'}
    
    def convert_to_search_strategy(self, user_input: str, database: str, detected_field: str = '') -> str:
        """
        将用户自然语言输入转换为特定数据库的检索式
        """
        try:
            logger.info(f"为数据库 {database} 转换检索式: {user_input}")
            
            # 根据不同数据库生成不同的检索式
            if database.lower() == 'pubmed':
                return self._convert_to_pubmed_strategy(user_input, detected_field)
            elif database.lower() == 'arxiv':
                return self._convert_to_arxiv_strategy(user_input, detected_field)
            elif database.lower() == 'semantic_scholar':
                return self._convert_to_semantic_scholar_strategy(user_input, detected_field)
            elif database.lower() == 'openalex':
                return self._convert_to_openalex_strategy(user_input, detected_field)
            elif database.lower() == 'doaj':
                return self._convert_to_doaj_strategy(user_input, detected_field)
            else:
                # 默认返回优化后的通用检索式
                return self._convert_to_general_strategy(user_input, detected_field)
                
        except Exception as e:
            logger.error(f"转换检索式时出错: {e}")
            return user_input  # 回退到原始输入
    
    def _convert_to_pubmed_strategy(self, user_input: str, field: str) -> str:
        """转换为PubMed检索式（使用app.py中现有的提示词）"""
        prompt = f"""作为PubMed搜索专家，请为以下研究内容生成优化的PubMed检索策略：

研究内容：{user_input}

要求：
1. 提取2-3个核心概念，每个概念扩展：
   - 首选缩写（如有）
   - 全称术语
   - 相近术语和同义词
   - 仅返回检索策略，不要其他解释

2. 结构要求：
   (
     ("缩写"[Title/Abstract] OR "全称术语"[Title/Abstract] OR "同义词"[Title/Abstract])
     AND
     ("缩写"[Title/Abstract] OR "全称术语"[Title/Abstract] OR "同义词"[Title/Abstract])
   )

3. 强制规则：
   - 每个概念最多3个术语（缩写+全称+同义词）
   - 只使用Title/Abstract字段，不使用MeSH
   - 保持AND连接的逻辑组不超过3组
   - 使用精确匹配，所有术语都要加双引号"""

        try:
            strategy = call_deepseek_api(prompt)
            return strategy.strip()
        except Exception as e:
            logger.error(f"生成PubMed检索式失败: {e}")
            return user_input
    
    def _convert_to_arxiv_strategy(self, user_input: str, field: str) -> str:
        """转换为arXiv检索式"""
        prompt = f"""
作为arXiv预印本数据库搜索专家，请将以下自然语言查询转换为专门适用于arXiv数据库的检索策略：

用户查询："{user_input}"
研究领域：{field}

**重要：这是专门为arXiv数据库设计的检索式，请严格按照arXiv搜索语法：**

1. 优先使用arXiv分类代码：
   - 计算机科学：cs.AI, cs.LG, cs.CV, cs.CL等
   - 数学：math.ST, math.NA, math.OC等
   - 物理学：physics.optics, cond-mat, hep-th等
2. 使用关键词组合，适合理工科术语
3. 考虑技术术语和学科特定词汇
4. 可以使用字段搜索：ti: (标题), abs: (摘要), au: (作者)

**输出要求：**
- 只返回最终的arXiv检索式
- 不要包含任何解释文字
- 检索式必须适合arXiv数据库
- 示例格式：cat:cs.LG AND "deep learning" 或 ti:"neural networks" AND abs:optimization

请生成arXiv检索式：
"""
        
        try:
            strategy = call_deepseek_api(prompt)
            return strategy.strip()
        except Exception as e:
            logger.error(f"生成arXiv检索式失败: {e}")
            return user_input
    
    def _convert_to_semantic_scholar_strategy(self, user_input: str, field: str) -> str:
        """转换为Semantic Scholar检索式"""
        prompt = f"""
作为Semantic Scholar AI学术搜索专家，请将以下自然语言查询转换为专门适用于Semantic Scholar数据库的检索策略：

用户查询："{user_input}"
研究领域：{field}

**重要：这是专门为Semantic Scholar数据库设计的检索式，该数据库特别适合计算机科学和AI领域：**

1. 使用清晰的关键词组合，特别是计算机科学和AI术语
2. 使用引号包围精确短语，如："machine learning"
3. 合理使用布尔操作符（AND, OR）
4. 考虑技术同义词和相关概念
5. 适合AI、机器学习、数据科学等领域的术语

**输出要求：**
- 只返回最终的检索式
- 不要包含任何解释文字
- 检索式必须适合Semantic Scholar数据库
- 示例格式："machine learning" AND "neural networks" OR "deep learning" AND optimization

请生成Semantic Scholar检索式：
"""
        
        try:
            strategy = call_deepseek_api(prompt)
            return strategy.strip()
        except Exception as e:
            logger.error(f"生成Semantic Scholar检索式失败: {e}")
            return user_input
    
    def _convert_to_openalex_strategy(self, user_input: str, field: str) -> str:
        """转换为OpenAlex检索式"""
        prompt = f"""
作为OpenAlex全学科数据库搜索专家，请将以下自然语言查询转换为专门适用于OpenAlex数据库的检索策略：

用户查询："{user_input}"
研究领域：{field}

**重要：这是专门为OpenAlex全学科数据库设计的检索式，该数据库覆盖所有学科领域：**

1. 使用广泛的学术术语，适合跨学科搜索
2. 考虑多学科的关键词组合
3. 使用清晰的概念组合，避免过于专业的术语
4. 适合全学科搜索的通用性表达
5. 平衡查全率和查准率，确保覆盖面广

**输出要求：**
- 只返回最终的检索式
- 不要包含任何解释文字
- 检索式必须适合OpenAlex全学科数据库
- 使用通用的学术术语，避免特定数据库的语法
- 示例格式：climate change environmental impact sustainability

请生成OpenAlex检索式：
"""
        
        try:
            strategy = call_deepseek_api(prompt)
            return strategy.strip()
        except Exception as e:
            logger.error(f"生成OpenAlex检索式失败: {e}")
            return user_input
    
    def _convert_to_doaj_strategy(self, user_input: str, field: str) -> str:
        """转换为DOAJ检索式"""
        prompt = f"""
作为DOAJ开放获取期刊数据库搜索专家，请将以下自然语言查询转换为专门适用于DOAJ数据库的检索策略：

用户查询："{user_input}"
研究领域：{field}

**重要：这是专门为DOAJ开放获取期刊数据库设计的检索式，该数据库专注于高质量的开放获取学术期刊：**

1. 使用开放获取期刊中常见的学术术语
2. 考虑国际化和多语言的表达方式
3. 使用清晰的学术概念，适合期刊文章搜索
4. 注重高质量同行评议内容的关键词
5. 适合各学科领域的开放获取研究

**输出要求：**
- 只返回最终的检索式
- 不要包含任何解释文字
- 检索式必须适合DOAJ开放获取期刊数据库
- 使用标准的学术术语
- 示例格式：sustainable development open access research policy

请生成DOAJ检索式：
"""
        
        try:
            strategy = call_deepseek_api(prompt)
            return strategy.strip()
        except Exception as e:
            logger.error(f"生成DOAJ检索式失败: {e}")
            return user_input
    
    def _convert_to_general_strategy(self, user_input: str, field: str) -> str:
        """转换为通用检索式"""
        prompt = f"""
作为学术搜索专家，请将以下自然语言查询转换为优化的学术检索策略：

用户查询："{user_input}"
研究领域：{field}

请生成通用的学术检索式，要求：
1. 提取核心概念和关键词
2. 使用学术术语和专业词汇
3. 考虑同义词和相关术语
4. 使用适当的逻辑组合
5. 确保检索式的通用性和有效性

请只返回最终的检索式，不要包含其他解释文字。
"""
        
        try:
            strategy = call_deepseek_api(prompt)
            return strategy.strip()
        except Exception as e:
            logger.error(f"生成通用检索式失败: {e}")
            return user_input
    
    def _extract_field_from_analysis(self, analysis_text: str) -> str:
        """从分析结果中提取研究领域"""
        try:
            # 查找研究领域识别部分
            field_match = re.search(r'\*\*研究领域识别：\*\*\s*([^\n]+)', analysis_text)
            if field_match:
                return field_match.group(1).strip()
        except:
            pass
        return '综合'
    
    def _extract_single_database_from_analysis(self, analysis_text: str) -> str:
        """从分析结果中提取推荐的单个数据库"""
        try:
            # 查找最佳数据库部分
            db_match = re.search(r'\*\*最佳数据库：\*\*\s*([^\n]+)', analysis_text)
            if db_match:
                db_text = db_match.group(1).strip().lower()

                # 扩展的数据库名称映射，包含各种可能的表达方式
                db_mapping = {
                    'pubmed': 'pubmed',
                    'pub med': 'pubmed',
                    'medline': 'pubmed',
                    'arxiv': 'arxiv',
                    'ar xiv': 'arxiv',
                    'semantic scholar': 'semantic_scholar',
                    'semanticscholar': 'semantic_scholar',
                    'semantic': 'semantic_scholar',
                    'openalex': 'openalex',
                    'open alex': 'openalex',
                    'doaj': 'doaj',
                    'directory of open access journals': 'doaj'
                }

                # 查找匹配的数据库（优先精确匹配）
                for db_name, db_key in db_mapping.items():
                    if db_name == db_text or db_name in db_text:
                        logger.info(f"匹配到数据库: {db_text} -> {db_key}")
                        return db_key

                # 如果没有精确匹配，尝试部分匹配
                if 'pubmed' in db_text or 'medline' in db_text:
                    return 'pubmed'
                elif 'arxiv' in db_text:
                    return 'arxiv'
                elif 'semantic' in db_text:
                    return 'semantic_scholar'
                elif 'openalex' in db_text or 'alex' in db_text:
                    return 'openalex'
                elif 'doaj' in db_text or 'open access' in db_text:
                    return 'doaj'

        except Exception as e:
            logger.error(f"解析数据库名称时出错: {e}")

        return ''

    def _extract_databases_from_analysis(self, analysis_text: str) -> List[str]:
        """从分析结果中提取推荐的数据库（保留用于兼容性）"""
        try:
            # 查找推荐数据库部分
            db_match = re.search(r'\*\*推荐数据库：\*\*\s*([^\n]+)', analysis_text)
            if db_match:
                db_text = db_match.group(1).strip()
                # 提取数据库名称
                databases = []
                db_mapping = {
                    'pubmed': 'pubmed',
                    'arxiv': 'arxiv',
                    'semantic scholar': 'semantic_scholar',
                    'openalex': 'openalex',
                    'doaj': 'doaj'
                }

                for db_name, db_key in db_mapping.items():
                    if db_name.lower() in db_text.lower():
                        databases.append(db_key)

                return databases[:3]  # 最多返回3个数据库
        except:
            pass
        return []
    
    def _keyword_based_single_selection(self, user_input: str) -> str:
        """基于关键词的单个数据库选择（备选方案）"""
        input_lower = user_input.lower()
        scores = {}

        for db_name, db_info in self.database_keywords.items():
            score = 0
            for keyword in db_info['keywords']:
                if keyword.lower() in input_lower:
                    score += 1

            if score > 0:
                # 考虑数据库优先级
                scores[db_name] = score * (10 - db_info['priority'])  # 优先级越高，权重越大

        # 返回得分最高的数据库
        if scores:
            best_db = max(scores.items(), key=lambda x: x[1])[0]
            return best_db
        else:
            return 'openalex'  # 默认使用OpenAlex作为通用数据库

    def _keyword_based_selection(self, user_input: str) -> List[str]:
        """基于关键词的数据库选择（备选方案，保留用于兼容性）"""
        input_lower = user_input.lower()
        scores = {}

        for db_name, db_info in self.database_keywords.items():
            score = 0
            for keyword in db_info['keywords']:
                if keyword.lower() in input_lower:
                    score += 1

            if score > 0:
                scores[db_name] = score

        # 按分数排序并返回前3个
        sorted_dbs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [db[0] for db in sorted_dbs[:3]] if sorted_dbs else ['openalex']
    
    def _detect_field_by_keywords(self, user_input: str) -> str:
        """基于关键词检测研究领域"""
        input_lower = user_input.lower()
        
        field_keywords = {
            '医学': ['医学', '临床', '疾病', '治疗', '药物', '患者'],
            '计算机科学': ['计算机', '算法', '人工智能', '机器学习', '软件'],
            '物理学': ['物理', '量子', '粒子', '能量', '力学'],
            '数学': ['数学', '方程', '定理', '统计', '概率'],
            '生物学': ['生物', '基因', '蛋白质', '细胞', '分子']
        }
        
        for field, keywords in field_keywords.items():
            if any(keyword in input_lower for keyword in keywords):
                return field
        
        return '综合'


# 全局路由器实例
search_router = IntelligentSearchRouter()
