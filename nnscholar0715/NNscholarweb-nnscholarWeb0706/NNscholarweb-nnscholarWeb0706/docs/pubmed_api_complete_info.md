# PubMed API 完整信息说明

## 概述
PubMed API (E-utilities) 提供了访问NCBI数据库的完整接口，可以获取非常详细的文献信息。以下是通过PubMed API可以获取的所有信息类型。

## 1. 基本文献标识信息

### 1.1 唯一标识符
- **PMID** (PubMed ID) - PubMed唯一标识符
- **PMC ID** - PubMed Central ID（如果文章在PMC中）
- **DOI** - 数字对象标识符
- **PII** - Publisher Item Identifier
- **Other IDs** - 其他数据库ID（如Scopus、Web of Science等）

### 1.2 版本信息
- **Version** - 文章版本号
- **Status** - 发表状态（如In-Process, MEDLINE, PubMed-not-MEDLINE）
- **Owner** - 数据所有者（如NLM, NASA, PIP等）

## 2. 文章内容信息

### 2.1 标题和摘要
- **ArticleTitle** - 文章标题
- **VernacularTitle** - 本地语言标题
- **Abstract** - 摘要（可能包含结构化部分）
  - Background/Objective - 背景/目标
  - Methods - 方法
  - Results - 结果
  - Conclusions - 结论
  - Copyright Information - 版权信息

### 2.2 语言信息
- **Language** - 文章语言
- **OriginalLanguage** - 原始语言（如果是翻译）

## 3. 作者和机构信息

### 3.1 作者详细信息
- **LastName** - 姓
- **ForeName** - 名
- **Initials** - 姓名缩写
- **Suffix** - 后缀（如Jr., Sr., III等）
- **CollectiveName** - 集体作者名
- **Identifier** - 作者标识符（如ORCID）

### 3.2 机构信息
- **Affiliation** - 作者机构
- **AffiliationInfo** - 详细机构信息
  - Institution - 机构名称
  - Country - 国家
  - Identifier - 机构标识符

### 3.3 通讯作者
- **CorrespondingAuthor** - 通讯作者标识
- **ContactInformation** - 联系信息

## 4. 期刊和出版信息

### 4.1 期刊基本信息
- **Journal Title** - 期刊全名
- **ISOAbbreviation** - ISO缩写
- **MedlineAbbreviation** - Medline缩写
- **ISSN** - 印刷版ISSN
- **ESSN** - 电子版ISSN
- **Publisher** - 出版商

### 4.2 期刊分类
- **JournalIssue** - 期刊期号信息
  - Volume - 卷号
  - Issue - 期号
  - PubDate - 发表日期
  - Season - 季节（如Spring, Summer等）

### 4.3 出版状态
- **PublicationStatus** - 出版状态
- **History** - 发表历史
  - Received - 收稿日期
  - Accepted - 接收日期
  - Revised - 修订日期
  - Published - 发表日期
  - Electronic Publication - 电子发表日期

## 5. 分类和索引信息

### 5.1 MeSH术语 (Medical Subject Headings)
- **MeshHeading** - MeSH主题词
  - DescriptorName - 描述符名称
  - QualifierName - 限定词
  - MajorTopicYN - 是否为主要主题
  - UI - 唯一标识符

### 5.2 关键词
- **KeywordList** - 关键词列表
  - Keyword - 关键词
  - MajorTopicYN - 是否为主要主题
  - Owner - 关键词来源（如NOTNLM, NLM等）

### 5.3 化学物质
- **ChemicalList** - 化学物质列表
  - NameOfSubstance - 物质名称
  - RegistryNumber - 注册号
  - UI - 唯一标识符

### 5.4 基因信息
- **GeneSymbolList** - 基因符号列表
- **ProteinList** - 蛋白质列表

## 6. 文献类型和研究设计

### 6.1 发表类型
- **PublicationType** - 发表类型
  - Journal Article - 期刊文章
  - Review - 综述
  - Meta-Analysis - 荟萃分析
  - Clinical Trial - 临床试验
  - Case Reports - 病例报告
  - Editorial - 社论
  - Letter - 信件
  - Comment - 评论
  - Retracted Publication - 撤稿文章

### 6.2 研究类型
- **StudyType** - 研究类型
- **StudyDesign** - 研究设计
- **DataBankList** - 数据库列表（如临床试验注册号）

## 7. 引用和关联信息

### 7.1 引用关系
- **CitationSubset** - 引用子集
- **CommentsCorrectionsList** - 评论和更正列表
  - CommentOn - 评论的文章
  - ErratumFor - 勘误的文章
  - ReprintOf - 重印的文章
  - RetractionOf - 撤回的文章

### 7.2 相关文章
- **SimilarArticles** - 相似文章
- **CitedByArticles** - 被引用文章
- **ReferencedArticles** - 引用的文章

## 8. 特殊标记和注释

### 8.1 质量标记
- **QualityReporting** - 质量报告
- **EvidenceLevel** - 证据级别
- **StudyCharacteristics** - 研究特征

### 8.2 特殊注释
- **GeneralNote** - 一般注释
- **PersonalNameSubject** - 个人姓名主题
- **InvestigatorList** - 研究者列表
- **SpaceFlightMission** - 太空飞行任务（NASA文献）

## 9. 技术和元数据

### 9.1 处理信息
- **DateCreated** - 创建日期
- **DateCompleted** - 完成日期
- **DateRevised** - 修订日期
- **IndexingMethod** - 索引方法

### 9.2 数据来源
- **DataSource** - 数据来源
- **Country** - 国家信息
- **MedlineJournalInfo** - Medline期刊信息

## 10. 补充材料

### 10.1 附加信息
- **SupplementaryMaterial** - 补充材料
- **DataAvailability** - 数据可用性声明
- **FundingInformation** - 资助信息
- **ConflictOfInterest** - 利益冲突声明

### 10.2 多媒体内容
- **Figures** - 图片信息
- **Tables** - 表格信息
- **VideoLinks** - 视频链接

## 11. 访问和权限信息

### 11.1 开放获取
- **OpenAccess** - 开放获取状态
- **License** - 许可证信息
- **Copyright** - 版权信息

### 11.2 全文链接
- **FullTextLinks** - 全文链接
- **PMCLinks** - PMC链接
- **PublisherLinks** - 出版商链接

## 12. 我们系统当前提取的信息

基于代码分析，我们的系统目前提取以下信息：

✅ **已实现提取：**
- PMID, 标题, 作者, 期刊, 摘要, DOI
- 发表日期和年份
- ISSN/eISSN
- 关键词（多层后备机制）
- MeSH术语
- 期刊指标（影响因子、JCR分区、CAS分区）

🔄 **可以扩展提取：**
- 更详细的作者机构信息
- 发表类型和研究类型
- 化学物质和基因信息
- 引用关系
- 资助信息
- 开放获取状态

这个完整的信息列表展示了PubMed API的强大功能，几乎涵盖了学术文献的所有重要方面。

## 13. 实际XML结构示例

以下是PubMed API返回的典型XML结构：

```xml
<PubmedArticle>
    <MedlineCitation Status="MEDLINE" Owner="NLM">
        <PMID Version="1">12345678</PMID>
        <DateCompleted>
            <Year>2024</Year>
            <Month>01</Month>
            <Day>15</Day>
        </DateCompleted>
        <Article PubModel="Print-Electronic">
            <Journal>
                <ISSN IssnType="Electronic">1476-4687</ISSN>
                <JournalIssue CitedMedium="Internet">
                    <Volume>625</Volume>
                    <Issue>7993</Issue>
                    <PubDate>
                        <Year>2024</Year>
                        <Month>Jan</Month>
                    </PubDate>
                </JournalIssue>
                <Title>Nature</Title>
                <ISOAbbreviation>Nature</ISOAbbreviation>
            </Journal>
            <ArticleTitle>Machine learning applications in medical diagnosis.</ArticleTitle>
            <AuthorList CompleteYN="Y">
                <Author ValidYN="Y">
                    <LastName>Smith</LastName>
                    <ForeName>John</ForeName>
                    <Initials>J</Initials>
                    <AffiliationInfo>
                        <Affiliation>Department of Computer Science, University of Example.</Affiliation>
                    </AffiliationInfo>
                </Author>
            </AuthorList>
            <Abstract>
                <AbstractText Label="BACKGROUND">Background information...</AbstractText>
                <AbstractText Label="METHODS">Methods description...</AbstractText>
                <AbstractText Label="RESULTS">Results summary...</AbstractText>
                <AbstractText Label="CONCLUSIONS">Conclusions...</AbstractText>
            </Abstract>
        </Article>
        <MeshHeadingList>
            <MeshHeading>
                <DescriptorName UI="D000001" MajorTopicYN="Y">Machine Learning</DescriptorName>
            </MeshHeading>
        </MeshHeadingList>
        <KeywordList Owner="NOTNLM">
            <Keyword MajorTopicYN="N">artificial intelligence</Keyword>
            <Keyword MajorTopicYN="Y">medical diagnosis</Keyword>
        </KeywordList>
    </MedlineCitation>
    <PubmedData>
        <History>
            <PubMedPubDate PubStatus="received">
                <Year>2023</Year>
                <Month>10</Month>
                <Day>15</Day>
            </PubMedPubDate>
            <PubMedPubDate PubStatus="accepted">
                <Year>2023</Year>
                <Month>12</Month>
                <Day>20</Day>
            </PubMedPubDate>
        </History>
        <PublicationStatus>ppublish</PublicationStatus>
        <ArticleIdList>
            <ArticleId IdType="pubmed">12345678</ArticleId>
            <ArticleId IdType="doi">10.1038/s41586-024-07001-0</ArticleId>
            <ArticleId IdType="pmc">PMC10123456</ArticleId>
        </ArticleIdList>
    </PubmedData>
</PubmedArticle>
```

## 14. API调用示例

### 14.1 搜索文献 (ESearch)
```
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?
db=pubmed&
term=machine+learning+medical+diagnosis&
retmax=100&
retmode=xml
```

### 14.2 获取详细信息 (EFetch)
```
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?
db=pubmed&
id=12345678,23456789&
retmode=xml&
rettype=abstract
```

### 14.3 获取相关文章 (ELink)
```
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?
dbfrom=pubmed&
db=pubmed&
id=12345678&
cmd=neighbor
```

## 15. 数据质量和完整性

### 15.1 数据完整性
- **MEDLINE记录** - 完整索引，包含所有MeSH术语
- **In-Process记录** - 正在处理中，可能缺少某些字段
- **PubMed-not-MEDLINE** - 不在MEDLINE中，信息可能有限

### 15.2 数据更新频率
- **每日更新** - 新文献每日添加
- **回溯更新** - 历史文献的信息可能会更新
- **实时索引** - 某些期刊的文章可能实时添加

这个完整的信息说明展示了PubMed API提供的丰富数据，为学术研究和文献分析提供了强大的数据基础。
