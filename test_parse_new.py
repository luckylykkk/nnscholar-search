#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import re

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_recommendations_to_structured_data(recommendations_text, original_papers):
    """将推荐文本解析为结构化数据"""
    try:
        logger.info(f"开始解析推荐结果，原始文献数量: {len(original_papers)}")
        
        # 使用换行符分割文本
        lines = recommendations_text.split('\n')
        recommended_papers = []
        
        current_paper = None
        current_section = None
        content_buffer = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检测文献标题行
            if line.startswith(('1. **', '2. **', '3. **', '4. **', '5. **')):
                # 保存上一篇文献
                if current_paper:
                    if current_section == 'reason' and content_buffer:
                        current_paper['reason'] = ' '.join(content_buffer).strip()
                    recommended_papers.append(current_paper)
                
                # 开始新文献
                title_match = re.search(r'\d+\.\s*\*\*(.*?)\*\*', line)
                if title_match:
                    title = title_match.group(1).strip()
                    current_paper = {
                        'title': title,
                        'chinese_title': '',
                        'authors': '',
                        'abstract': '',
                        'reason': ''
                    }
                    current_section = None
                    content_buffer = []
                    print(f"找到文献: {title}")
                
            # 检测中文标题（方括号格式）
            elif line.startswith('[') and line.endswith(']') and current_paper:
                current_paper['chinese_title'] = line[1:-1]  # 去掉方括号
                print(f"找到中文标题: {current_paper['chinese_title']}")
                
            # 检测各个部分
            elif line.startswith('**作者信息**'):
                current_section = 'authors'
                content_buffer = []
            elif line.startswith('**期刊信息**'):
                if current_section == 'authors' and content_buffer:
                    current_paper['authors'] = ' '.join(content_buffer).strip()
                current_section = 'journal'
                content_buffer = []
            elif line.startswith('**中文摘要总结**') or line.startswith('**摘要**'):
                current_section = 'abstract'
                content_buffer = []
            elif line.startswith('**推荐理由**'):
                if current_section == 'abstract' and content_buffer:
                    current_paper['abstract'] = ' '.join(content_buffer).strip()
                current_section = 'reason'
                content_buffer = []
            elif line.startswith('---'):
                if current_section == 'reason' and content_buffer:
                    current_paper['reason'] = ' '.join(content_buffer).strip()
                current_section = None
                content_buffer = []
            elif line.startswith('📊') or line.startswith('🎯'):
                if current_section == 'reason' and content_buffer:
                    current_paper['reason'] = ' '.join(content_buffer).strip()
                break
            elif current_section and not line.startswith('**'):
                content_buffer.append(line)
        
        # 处理最后一篇文献
        if current_paper:
            if current_section == 'reason' and content_buffer:
                current_paper['reason'] = ' '.join(content_buffer).strip()
            elif current_section == 'abstract' and content_buffer:
                current_paper['abstract'] = ' '.join(content_buffer).strip()
            recommended_papers.append(current_paper)
        
        logger.info(f"解析出 {len(recommended_papers)} 篇推荐文献")
        
        # 打印解析结果
        for i, paper in enumerate(recommended_papers):
            print(f"\n=== 第 {i+1} 篇文献 ===")
            print(f"标题: {paper.get('title', 'N/A')}")
            print(f"中文标题: {paper.get('chinese_title', 'N/A')}")
            print(f"作者: {paper.get('authors', 'N/A')}")
            print(f"摘要: {paper.get('abstract', 'N/A')[:100]}...")
            print(f"推荐理由: {paper.get('reason', 'N/A')[:100]}...")
        
        return recommended_papers
        
    except Exception as e:
        logger.error(f"解析推荐结果时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

# 测试文本 - 使用实际AI返回的内容
test_text = """📚 代表性文章推荐

🏆 最具代表性的5篇文章

1. **Long-Term Prognostic Utility of Coronary CT Angiography in Stable Patients With Diabetes Mellitus**
[长期预后价值：冠状动脉CT血管造影在稳定型糖尿病患者中的应用]

**期刊信息**
影响因子：12.800 | JCR分区：Q1 | 中科院分区：B1区 | 发表年份：2016

**中文摘要总结**
本研究评估了冠状动脉CT血管造影(CCTA)对糖尿病患者长期预后的预测价值。通过国际多中心CONFIRM注册研究，对1,823名糖尿病患者和1,823名非糖尿病患者进行5年随访。结果显示，无冠脉疾病的糖尿病患者死亡风险与非糖尿病患者相当；而非阻塞性和阻塞性冠脉疾病患者的死亡风险显著增加。特别值得注意的是，糖尿病患者即使仅有非阻塞性病变，其死亡风险也高于非糖尿病患者的阻塞性病变。研究证实CCTA对糖尿病患者具有重要的长期预后价值。

**推荐理由**
1) 创新点：首次大规模比较糖尿病患者与非糖尿病患者CCTA结果的长期预后差异
2) 学术价值：发表在心血管顶级期刊(JACC)，为糖尿病患者的冠脉评估提供重要循证依据
3) 影响力：研究结果改变了临床对糖尿病患者冠脉病变风险分层的认识
4) 方法学：采用国际多中心数据，严格的倾向匹配设计，随访时间长(5年)

---

2. **Prognostic Value of Coronary Computed Tomography Angiography in Diabetic Patients: A Meta-analysis**
[糖尿病患者冠状动脉CT血管造影预后价值的Meta分析]

**期刊信息**
影响因子：14.800 | JCR分区：Q1 | 中科院分区：B1区 | 发表年份：2016

**中文摘要总结**
这项Meta分析纳入8项研究共6,225名糖尿病患者，评估CCTA对心血管事件的预测价值。结果显示，阻塞性冠脉疾病(38%)和非阻塞性病变(36%)在糖尿病患者中普遍存在。阻塞性病变患者的年事件率高达17.1%，而非阻塞性病变和正常冠脉分别为4.5%和0.1%。CCTA可安全排除未来事件，并能识别需要强化治疗的高危患者。研究强调CCTA在糖尿病患者风险分层中的关键作用。

**推荐理由**
1) 创新点：首个针对糖尿病患者CCTA预后价值的系统评价
2) 学术价值：发表在糖尿病领域顶级期刊(Diabetes Care)，证据等级高
3) 影响力：为临床指南制定提供了重要依据
4) 方法学：采用严格的Meta分析方法，样本量大，结果可靠

---

3. **Effect of screening for coronary artery disease using CT angiography on mortality and cardiac events in high-risk patients with diabetes: the FACTOR-64 randomized clinical trial**
[高风险糖尿病患者使用CT血管造影筛查冠脉疾病对死亡率和心脏事件的影响：FACTOR-64随机临床试验]

**期刊信息**
影响因子：63.100 | JCR分区：Q1 | 中科院分区：B1区 | 发表年份：2014

**摘要**
Coronary artery disease (CAD) is a major cause of cardiovascular morbidity and mortality in patients with diabetes mellitus, yet CAD often is asymptomatic prior to myocardial infarction (MI) and coronary death.To assess whether routine screening for CAD by coronary computed tomography angiography (CCTA) in patients with type 1 or type 2 diabetes deemed to be at high cardiac risk followed by CCTA-directed therapy would reduce the risk of death and nonfatal coronary outcomes.

**推荐理由**
1) 创新点：首个评估CCTA筛查对无症状糖尿病患者预后影响的大规模RCT研究
2) 学术价值：发表在JAMA主刊，方法学严谨，临床指导意义重大
3) 影响力：研究结果直接影响了临床实践指南
4) 方法学：多中心随机对照设计，随访时间长，结果可靠

---

4. **Coronary Computed Tomography (CT) Angiography as a Predictor of Cardiac and Noncardiac Vascular Events in Asymptomatic Type 2 Diabetics: A 7-Year Population-Based Cohort Study**

**期刊信息**
影响因子：5.000 | JCR分区：Q1 | 中科院分区：B1区 | 发表年份：2016

**摘要**
Type 2 diabetics are at increased risk for vascular events, but the value of further risk stratification for coronary heart disease (CHD) in asymptomatic subjects is unclear. We examined the added value of coronary computed tomography angiography over clinical risk scores (United Kingdom Prospective Diabetes Study), and coronary artery calcium in a population-based cohort of asymptomatic type 2 diabetics.

**推荐理由**
1) 创新点：首次在无症状糖尿病患者中比较CCTA与传统风险评估工具的预测价值
2) 学术价值：长期随访(7年)的队列研究，证据等级高
3) 影响力：为无症状糖尿病患者的筛查策略提供了新思路
4) 方法学：采用先进斑块分析技术，评估指标全面

---

5. **Impact of diabetes duration on the extent and severity of coronary atheroma burden and long-term clinical outcome in asymptomatic type 2 diabetic patients: evaluation by Coronary CT angiography**

**期刊信息**
影响因子：6.700 | JCR分区：Q1 | 中科院分区：B1区 | 发表年份：2015

**摘要**
We investigated the association between diabetes duration and the extent and severity of coronary artery disease (CAD) as well as long-term clinical outcomes using coronary computed tomography angiography (CCTA) in asymptomatic type 2 diabetic patients.

**推荐理由**
1) 创新点：首次系统评估糖尿病病程与冠脉病变程度及预后的关系
2) 学术价值：发表在EHJ，样本量大(n=933)，随访时间长
3) 影响力：为糖尿病患者的个体化风险评估提供了重要依据
4) 方法学：采用多种定量指标全面评估冠脉病变

---

📊 **筛选标准说明**
• 影响因子权重：30%（期刊影响力和声誉）
• 创新性权重：40%（研究方法和结果的创新程度）
• 学术质量权重：30%（研究设计、数据分析和结论可靠性）

🎯 **推荐总结**
**整体评价：** 推荐的5篇文献代表了当前CCTA在糖尿病患者冠脉评估领域最高水平的研究，包括大规模队列研究、Meta分析和RCT研究，证据等级高，临床指导意义重大。
**研究趋势：** 从单纯诊断价值评估转向预后预测和临床决策支持；从单纯解剖评估转向综合斑块特征分析；关注无症状高风险人群的筛查价值。
**建议关注：** 1) CCTA在糖尿病患者风险分层中的独特价值 2) 斑块特征分析对预后的预测作用 3) 糖尿病患者冠脉病变的特殊性 4) 筛查策略的成本效益分析

*注：所有推荐文献均来自提供的80篇候选文献，按照专业评估标准进行筛选。*"""

if __name__ == "__main__":
    print("开始测试解析函数...")
    result = parse_recommendations_to_structured_data(test_text, [])
    print(f"\n总共解析出 {len(result)} 篇文献")
