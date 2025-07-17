// 重新定义的loadAnalysisCards函数，与openAnalysisFeature()保持一致
function loadAnalysisCards() {
    const grid = document.querySelector('.analysis-grid');
    grid.innerHTML = `
        <div class="analysis-card" onclick="openAnalysisFeature('journal-selection')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">📊</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">AI投稿选刊</div>
            <div style="font-size: 0.7rem; color: #6b7280;">基于研究内容智能推荐合适的期刊</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('paper-translation')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">🌐</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">论文翻译</div>
            <div style="font-size: 0.7rem; color: #6b7280;">专业的学术论文中英文翻译</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('paper-polish')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">✨</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">论文润色</div>
            <div style="font-size: 0.7rem; color: #6b7280;">提升论文语言表达和学术规范</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('ai-topic-selection')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">💡</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">AI选题</div>
            <div style="font-size: 0.7rem; color: #6b7280;">发现创新研究方向和热点</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('innovation-analysis')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">🚀</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">创新点分析</div>
            <div style="font-size: 0.7rem; color: #6b7280;">识别研究的创新性和价值</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('cover-letter')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">✉️</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">Cover Letter</div>
            <div style="font-size: 0.7rem; color: #6b7280;">投稿信函专业撰写</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('reviewer-response')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">🔄</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">审稿回复</div>
            <div style="font-size: 0.7rem; color: #6b7280;">审稿人意见分析与回复</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('reference-matching')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">📚</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">参考文献匹配</div>
            <div style="font-size: 0.7rem; color: #6b7280;">为内容匹配权威文献</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('research-methodology')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">🔬</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">方法学指导</div>
            <div style="font-size: 0.7rem; color: #6b7280;">研究设计和方法选择建议</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('literature-screening')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">🔍</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">文献筛查</div>
            <div style="font-size: 0.7rem; color: #6b7280;">精准筛选相关文献</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('innovation-discovery')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">💡</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">创新点挖掘</div>
            <div style="font-size: 0.7rem; color: #6b7280;">挖掘创新点和发文方向</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('review-outline')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">📋</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">综述大纲</div>
            <div style="font-size: 0.7rem; color: #6b7280;">分析并生成结构化大纲</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('grant-proposal')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">💰</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">基金立项</div>
            <div style="font-size: 0.7rem; color: #6b7280;">撰写基金申请立项依据</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('review-draft')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">📝</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">综述初稿</div>
            <div style="font-size: 0.7rem; color: #6b7280;">撰写综述初稿</div>
        </div>
        <div class="analysis-card" onclick="openAnalysisFeature('research-gap-analysis')">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">🎯</div>
            <div style="font-weight: 600; margin-bottom: 0.25rem; font-size: 0.875rem;">研究空白分析</div>
            <div style="font-size: 0.7rem; color: #6b7280;">分析研究空白并提供切入点建议</div>
        </div>
    `;
}