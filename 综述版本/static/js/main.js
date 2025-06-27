// 初始化Socket.IO连接
const socket = io();

// 进度日志记录
let progressLogs = [];
const MAX_LOG_ENTRIES = 50;

// 调试函数：检查搜索结果数据
function debugSearchResultData() {
    console.log('开始调试搜索结果数据');
    
    // 检查window.searchResultData是否存在
    if (!window.searchResultData) {
        console.error('window.searchResultData不存在');
        return false;
    }
    
    // 检查数据格式
    console.log('searchResultData类型:', typeof window.searchResultData);
    console.log('searchResultData结构:', Object.keys(window.searchResultData));
    
    // 检查data字段
    if (!window.searchResultData.data) {
        console.error('window.searchResultData.data不存在');
        return false;
    }
    
    // 检查data是否为数组
    if (!Array.isArray(window.searchResultData.data)) {
        console.error('window.searchResultData.data不是数组');
        console.log('实际类型:', typeof window.searchResultData.data);
        return false;
    }
    
    // 检查数据长度
    console.log('数据长度:', window.searchResultData.data.length);
    
    // 检查第一个元素
    if (window.searchResultData.data.length > 0) {
        console.log('第一个元素结构:', Object.keys(window.searchResultData.data[0]));
        console.log('第一个元素标题:', window.searchResultData.data[0].title);
    }
    
    return window.searchResultData.data.length > 0;
}

// 添加进度日志
function addProgressLog(message, isError = false) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    
    // 创建日志条目
    const logEntry = {
        time: timeStr,
        message: message,
        isError: isError
    };
    
    // 添加到日志数组
    progressLogs.push(logEntry);
    
    // 如果日志条目超过最大数量，删除最早的条目
    if (progressLogs.length > MAX_LOG_ENTRIES) {
        progressLogs.shift();
    }
    
    // 更新日志显示
    updateProgressLogDisplay();
}

// 获取会话ID的函数
function getSessionId() {
    // 尝试从localStorage获取会话ID
    let sessionId = localStorage.getItem('nnscholar_session_id');
    
    // 如果没有会话ID，生成一个新的
    if (!sessionId) {
        sessionId = 'session_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('nnscholar_session_id', sessionId);
    }
    
    return sessionId;
}

// 处理选题生成按钮点击事件
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM加载完成，开始设置选题按钮事件监听器');
    
    // 获取按钮和结果容器
    const reviewTopicBtn = document.getElementById('generate-review-topic');
    const researchTopicBtn = document.getElementById('generate-research-topic');
    const outlineBtn = document.getElementById('generate-outline');
    const topicResult = document.getElementById('topic-result');
    const topicResultTitle = document.getElementById('topic-result-title');
    const topicResultContent = document.getElementById('topic-result-content');
    
    console.log('按钮元素状态:', {
        reviewTopicBtn: reviewTopicBtn ? '已找到' : '未找到',
        researchTopicBtn: researchTopicBtn ? '已找到' : '未找到',
        outlineBtn: outlineBtn ? '已找到' : '未找到',
        topicResult: topicResult ? '已找到' : '未找到'
    });
    
    // 如果找到按钮，添加点击事件处理
    if (reviewTopicBtn) {
        console.log('为综述选题按钮添加点击事件');
        reviewTopicBtn.addEventListener('click', function(event) {
            console.log('综述选题按钮被点击', event);
            generateTopic('review');
        });
    } else {
        console.error('未找到综述选题按钮，无法添加点击事件');
        // 尝试在整个文档中查找按钮
        const allButtons = document.querySelectorAll('button');
        console.log('文档中的所有按钮:', Array.from(allButtons).map(btn => ({
            id: btn.id,
            text: btn.textContent.trim(),
            visible: btn.offsetParent !== null
        })));
    }
    
    if (researchTopicBtn) {
        console.log('为论著选题按钮添加点击事件');
        researchTopicBtn.addEventListener('click', function(event) {
            console.log('论著选题按钮被点击', event);
            generateTopic('research');
        });
    } else {
        console.error('未找到论著选题按钮，无法添加点击事件');
    }
    
    if (outlineBtn) {
        console.log('为综述大纲按钮添加点击事件');
        outlineBtn.addEventListener('click', function(event) {
            console.log('综述大纲按钮被点击', event);
            
            // 检查是否有搜索结果
            if (!window.searchResultData || !window.searchResultData.data || window.searchResultData.data.length === 0) {
                console.warn('未找到搜索结果数据，无法生成大纲');
                showToast('请先执行检索并获取文献', 'warning');
                return;
            }
            
            // 创建弹出框
            const modal = document.createElement('div');
            modal.className = 'modal fade';
            modal.id = 'outlineTitleModal';
            modal.setAttribute('tabindex', '-1');
            modal.setAttribute('aria-labelledby', 'outlineTitleModalLabel');
            modal.setAttribute('aria-hidden', 'true');
            
            modal.innerHTML = `
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="outlineTitleModalLabel">输入综述题目</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
                        </div>
                        <div class="modal-body">
                            <div class="form-group">
                                <label for="outlineTitle" class="form-label">综述题目：</label>
                                <input type="text" class="form-control" id="outlineTitle" placeholder="请输入综述题目">
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" id="submitOutlineTitle">确定</button>
                        </div>
                    </div>
                </div>
            `;
            
            // 添加到文档
            document.body.appendChild(modal);
            
            // 显示弹出框
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();
            
            // 处理确定按钮点击
            document.getElementById('submitOutlineTitle').addEventListener('click', function() {
                const outlineTitle = document.getElementById('outlineTitle').value.trim();
                if (!outlineTitle) {
                    alert('请输入综述题目');
                    return;
                }
                
                // 隐藏弹出框
                bsModal.hide();
                
                // 移除弹出框
                setTimeout(() => {
                    modal.remove();
                }, 500);
                
                // 生成大纲
                generateTopic('outline', outlineTitle);
            });
        });
    } else {
        console.error('未找到综述大纲按钮，无法添加点击事件');
    }
    
    // 生成选题的函数
    async function generateTopic(type, customTitle = null) {
        console.log(`开始生成选题，类型: ${type}${customTitle ? ', 自定义题目: ' + customTitle : ''}`);
        try {
            // 检查是否有搜索结果
            console.log('检查搜索结果数据:', {
                windowHasSearchResultData: !!window.searchResultData,
                dataExists: window.searchResultData && !!window.searchResultData.data,
                dataLength: window.searchResultData && window.searchResultData.data ? window.searchResultData.data.length : 0
            });
            
            // 详细记录window对象中的所有相关变量
            console.log('window对象中的相关变量:', {
                hasSearchResultData: 'searchResultData' in window,
                hasSearchResults: 'searchResults' in window,
                searchResultDataType: window.searchResultData ? typeof window.searchResultData : 'undefined',
                searchResultsType: window.searchResults ? typeof window.searchResults : 'undefined'
            });
            
            // 调试搜索结果数据
            const dataValid = debugSearchResultData();
            if (!dataValid) {
                console.warn('搜索结果数据无效，尝试使用window.searchResults');
                
                // 尝试使用window.searchResults
                if (window.searchResults && Array.isArray(window.searchResults) && window.searchResults.length > 0) {
                    console.log('找到window.searchResults，长度:', window.searchResults.length);
                    window.searchResultData = { data: window.searchResults };
                    console.log('已创建searchResultData，使用searchResults作为数据源');
                } else {
                    console.error('无法找到有效的搜索结果数据');
                    showToast('请先执行检索并获取文献', 'warning');
                    return;
                }
            }
            
            if (!window.searchResultData || !window.searchResultData.data || window.searchResultData.data.length === 0) {
                console.warn('未找到搜索结果数据，无法生成选题');
                showToast('请先执行检索并获取文献', 'warning');
                return;
            }
            
            // 显示加载状态和时间估计
            console.log('显示加载状态');
            if (type === 'review' || type === 'research') {
                showLoading('正在生成选题建议，大约需要45秒，请耐心等待...');
            } else if (type === 'outline') {
                showLoading('正在生成综述大纲，大约需要5分钟，请耐心等待...');
            } else {
                showLoading('正在生成选题建议，请稍候...');
            }
            
            // 准备标题列表
            const titles = window.searchResultData.data.map(paper => paper.title);
            console.log(`提取了${titles.length}个文献标题`);
            console.log('前5个标题示例:', titles.slice(0, 5));
            
            // 获取会话ID
            const sessionId = getSessionId();
            console.log('当前会话ID:', sessionId);
            
            // 构建请求数据
            const requestData = {
                type: type,
                titles: titles
            };
            
            // 如果提供了自定义标题，添加到请求中
            if (customTitle) {
                requestData.custom_title = customTitle;
            }
            
            // 调用后端API
            console.log('准备调用后端API', requestData);
            const response = await fetch('/api/generate-topic', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'sid': sessionId
                },
                body: JSON.stringify(requestData)
            });
            
            console.log('API响应状态:', response.status);
            const result = await response.json();
            console.log('API响应结果:', result);
            
            if (result.success) {
                console.log('选题生成成功，更新UI');
                // 更新结果显示
                topicResultTitle.textContent = result.title;
                
                // 将内容中的换行符转换为HTML换行
                const formattedContent = result.content.replace(/\n/g, '<br>');
                topicResultContent.innerHTML = formattedContent;
                
                // 显示结果容器
                topicResult.style.display = 'block';
                console.log('结果容器显示状态已更新');
                
                // 滚动到结果区域
                topicResult.scrollIntoView({ behavior: 'smooth' });
                console.log('页面已滚动到结果区域');
                
                showToast('选题建议生成完成', 'success');
                
                // 如果是大纲类型，添加处理二级标题的功能
                if (type === 'outline') {
                    console.log('检测到综述大纲，准备处理二级标题并自动生成所有内容');
                    setTimeout(() => {
                        processOutlineHeadings(true); // 传入true表示自动生成所有内容
                    }, 1000); // 延迟1秒，确保DOM已更新
                }
            } else {
                console.error('API返回错误:', result.error);
                throw new Error(result.error || '生成选题失败');
            }
        } catch (error) {
            console.error('生成选题过程中发生错误:', error);
            showToast(error.message || '生成选题失败，请稍后重试', 'error');
        } finally {
            console.log('选题生成流程结束，隐藏加载状态');
            hideLoading();
        }
    }
    
    // 处理大纲中的标题，添加操作按钮
    async function processOutlineHeadings(autoGenerate = false) {
        console.log('开始处理大纲标题');
        
        try {
            // 获取大纲内容容器
            const outlineContainer = document.getElementById('topic-result-content');
            if (!outlineContainer) {
                console.error('未找到大纲内容容器');
                return;
            }
            
            // 获取原始内容
            const rawContent = outlineContainer.innerHTML;
            console.log('获取到原始内容，长度:', rawContent.length);
            
            // 创建用于存储各部分内容的容器
            const sectionsContainer = document.createElement('div');
            sectionsContainer.className = 'outline-sections mt-4';
            sectionsContainer.id = 'outline-sections-container';
            
            // 直接从文本内容中识别四个部分，不依赖HTML标题元素
            // 定义要识别的部分
            const sections = [
                { type: 'abstract', name: '摘要', keywords: ['摘要', 'abstract'], content: '' },
                { type: 'introduction', name: '前言', keywords: ['前言', '引言', 'introduction', '背景'], content: '' },
                { type: 'progress', name: '研究进展', keywords: ['研究进展', '研究现状', '文献综述', '研究方法'], content: '' },
                { type: 'conclusion', name: '结论', keywords: ['结论', '总结', '展望', 'conclusion'], content: '' }
            ];
            
            // 从原始内容中识别各部分
            const lines = rawContent.split(/<br\s*\/?>/i);
            console.log(`分割后得到${lines.length}行内容`);
            
            // 识别部分的正则表达式
            const sectionRegex = /([0-9]+\.\s*|#+\s*|^\s*-\s*|^\s*\*\s*)(摘要|前言|引言|背景|研究进展|研究现状|文献综述|研究方法|结论|总结|展望|abstract|introduction|conclusion)/i;
            
            // 当前处理的部分索引
            let currentSectionIndex = -1;
            let sectionsFound = 0;
            
            // 按行处理内容
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                if (!line) continue;
                
                // 检查是否是部分标题
                const match = line.match(sectionRegex);
                if (match) {
                    // 找到部分标题
                    const keyword = match[2].toLowerCase();
                    let matchedSection = -1;
                    
                    // 确定匹配的部分
                    for (let j = 0; j < sections.length; j++) {
                        if (sections[j].keywords.some(k => keyword.includes(k.toLowerCase()))) {
                            matchedSection = j;
                            break;
                        }
                    }
                    
                    if (matchedSection !== -1) {
                        currentSectionIndex = matchedSection;
                        sectionsFound++;
                        console.log(`找到${sections[currentSectionIndex].name}部分: ${line}`);
                        sections[currentSectionIndex].title = line;
                        sections[currentSectionIndex].content = line + '<br>';
                    }
                } else if (currentSectionIndex !== -1) {
                    // 将当前行添加到当前部分
                    sections[currentSectionIndex].content += line + '<br>';
                }
            }
            
            console.log(`总共找到${sectionsFound}个部分`);
            
            // 如果未找到任何部分，尝试根据内容结构自动分段
            if (sectionsFound === 0) {
                console.log('未找到任何部分，尝试自动分段');
                
                // 将大纲内容分为四个部分
                const totalLines = lines.filter(line => line.trim()).length;
                const linesPerSection = Math.ceil(totalLines / 4);
                
                let lineCount = 0;
                let sectionIndex = 0;
                
                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i].trim();
                    if (!line) continue;
                    
                    if (sectionIndex < sections.length) {
                        sections[sectionIndex].content += line + '<br>';
                        lineCount++;
                        
                        if (lineCount >= linesPerSection && sectionIndex < 3) {
                            sectionIndex++;
                            lineCount = 0;
                        }
                    }
                }
                
                // 设置默认标题
                sections[0].title = '1. 摘要';
                sections[1].title = '2. 前言';
                sections[2].title = '3. 研究进展';
                sections[3].title = '4. 结论与展望';
                
                sectionsFound = 4;
                console.log('自动分段完成');
            }
            
            // 创建各部分的可视化容器
            for (let i = 0; i < sections.length; i++) {
                const section = sections[i];
                if (section.content) {
                    // 创建该部分的可视化容器
                    const sectionContainer = document.createElement('div');
                    sectionContainer.className = `outline-section ${section.type}-section mb-4`;
                    sectionContainer.setAttribute('data-section-type', section.type);
                    
                    // 设置不同部分的样式
                    let sectionClass = '';
                    switch (section.type) {
                        case 'abstract': sectionClass = 'abstract-section'; break;
                        case 'introduction': sectionClass = 'introduction-section'; break;
                        case 'progress': sectionClass = 'research-section'; break;
                        case 'conclusion': sectionClass = 'conclusion-section'; break;
                    }
                    
                    // 创建部分内容
                    sectionContainer.innerHTML = `
                        <div class="card ${sectionClass}">
                            <div class="section-header card-header">
                                <h3>${section.name}</h3>
                                <div class="btn-group">
                                    <button class="btn btn-sm btn-outline-primary edit-section-btn">
                                        <i class="fas fa-edit"></i> 编辑
                                    </button>
                                    <button class="btn btn-sm btn-primary generate-section-btn" data-section-type="${section.type}">
                                        <i class="fas fa-pen"></i> 生成${section.name}内容
                                    </button>
                                </div>
                    </div>
                    <div class="card-body">
                                <div class="section-content">${section.content}</div>
                                <div class="edit-area" style="display: none;">
                                    <textarea class="form-control" rows="10">${section.content}</textarea>
                                    <div class="mt-2">
                                        <button class="btn btn-primary save-section-btn">保存</button>
                                        <button class="btn btn-secondary cancel-edit-btn">取消</button>
                                    </div>
                                </div>
                            </div>
                    </div>
                `;
                
                    // 添加到容器
                    sectionsContainer.appendChild(sectionContainer);
                }
            }
            
            // 添加完成综述按钮
            const completeButtonContainer = document.createElement('div');
            completeButtonContainer.className = 'text-center my-4';
            completeButtonContainer.innerHTML = `
                <button id="complete-review-btn" class="btn btn-lg btn-success">
                    <i class="fas fa-check-circle"></i> 完成综述
                </button>
            `;
            
            // 先找到topic-result元素
            const topicResult = document.getElementById('topic-result');
            
            // 在原大纲内容之后添加各部分容器
            if (topicResult) {
                // 隐藏原始内容
                outlineContainer.style.display = 'none';
                
                // 添加处理后的内容和按钮
                topicResult.appendChild(sectionsContainer);
                topicResult.appendChild(completeButtonContainer);
                
                // 添加编辑和生成功能
                setupSectionButtons(sectionsContainer);
                
                // 添加完成综述按钮事件
                setupCompleteButton(completeButtonContainer);
                
                console.log('大纲处理完成，已添加到页面');
                
                // 如果启用了自动生成，开始自动生成所有内容
                if (autoGenerate) {
                    setTimeout(() => {
                        autoGenerateCompleteReview(sections, sectionsContainer);
                    }, 1000); // 延迟1秒再开始自动生成
                }
            } else {
                console.error('未找到topic-result容器');
            }
        } catch (error) {
            console.error('处理综述大纲时出错:', error);
            showErrorMessage('处理大纲时出错: ' + error.message);
        }
    }
    
    // 自动生成完整综述的所有部分内容
    async function autoGenerateCompleteReview(sections, sectionsContainer) {
        showToast('开始自动生成综述所有部分内容，整个过程大约需要5-10分钟，请耐心等待...', 'info');
        
        try {
            // 1. 获取所有部分内容的生成按钮
            const generateButtons = sectionsContainer.querySelectorAll('.generate-section-btn');
            const sectionElements = Array.from(sectionsContainer.querySelectorAll('.outline-section'));
            
            // 2. 依次生成摘要、前言和结论
            for (const button of generateButtons) {
                const sectionType = button.getAttribute('data-section-type');
                
                // 跳过研究进展部分，稍后特殊处理
                if (sectionType === 'progress') continue;
                
                // 点击生成按钮
                console.log(`自动点击${sectionType}生成按钮`);
                button.click();
                
                // 等待生成完成
                await new Promise(resolve => setTimeout(resolve, 10000)); // 给每部分10秒生成时间
            }
            
            // 3. 处理研究进展部分
            const progressSection = sectionElements.find(elem => elem.getAttribute('data-section-type') === 'progress');
            if (progressSection) {
                // 首先点击研究进展生成按钮，解析次级标题
                const progressButton = progressSection.querySelector('.generate-section-btn');
                if (progressButton) {
                    console.log('自动点击研究进展生成按钮，解析次级标题');
                    progressButton.click();
                    
                    // 等待次级标题解析完成
                    await new Promise(resolve => setTimeout(resolve, 5000));
                    
                    // 查找研究进展部分的一键生成按钮
                    setTimeout(() => {
                        const generateAllButton = progressSection.querySelector('#generate-all-subsections');
                        if (generateAllButton) {
                            console.log('自动点击一键生成所有次级标题内容按钮');
                            generateAllButton.click();
                            
                            // 等待所有次级标题生成完成后，自动点击完成综述按钮
                            setTimeout(() => {
                                const completeButton = document.getElementById('complete-review-btn');
                                if (completeButton) {
                                    console.log('自动点击完成综述按钮');
                                    
                                    // 获取原始题目作为综述题目
                                    const topicTitle = document.getElementById('topic-result-title').textContent;
                                    
                                    // 保存题目，以便自动填充
                                    window.autoReviewTitle = topicTitle || '综述论文';
                                    
                                    // 点击完成按钮
                                    completeButton.click();
                                }
                            }, 60000); // 给次级标题生成留出1分钟时间
                        }
                    }, 1000);
                }
            }
        } catch (error) {
            console.error('自动生成综述内容时出错:', error);
            showErrorMessage('自动生成过程中出错: ' + error.message);
        }
    }
    
    // 设置各部分按钮的事件处理
    function setupSectionButtons(container) {
        // 添加编辑功能
        const editButtons = container.querySelectorAll('.edit-section-btn');
        editButtons.forEach(button => {
            button.addEventListener('click', function() {
                const section = button.closest('.outline-section');
                const contentElement = section.querySelector('.section-content');
                const editArea = section.querySelector('.edit-area');
                
                contentElement.style.display = 'none';
                editArea.style.display = 'block';
            });
        });
        
        // 添加保存功能
        const saveButtons = container.querySelectorAll('.save-section-btn');
        saveButtons.forEach(button => {
            button.addEventListener('click', function() {
                const section = button.closest('.outline-section');
                const contentElement = section.querySelector('.section-content');
                const editArea = section.querySelector('.edit-area');
                const textarea = editArea.querySelector('textarea');
                
                // 解析编辑后的内容
                contentElement.innerHTML = textarea.value;
                contentElement.style.display = 'block';
                editArea.style.display = 'none';
            });
        });
        
        // 添加取消功能
        const cancelButtons = container.querySelectorAll('.cancel-edit-btn');
        cancelButtons.forEach(button => {
            button.addEventListener('click', function() {
                const section = button.closest('.outline-section');
                const contentElement = section.querySelector('.section-content');
                const editArea = section.querySelector('.edit-area');
                
                contentElement.style.display = 'block';
                editArea.style.display = 'none';
            });
        });
        
        // 添加生成内容功能
        const generateButtons = container.querySelectorAll('.generate-section-btn');
        generateButtons.forEach(button => {
            button.addEventListener('click', function() {
                const sectionType = button.getAttribute('data-section-type');
                const section = button.closest('.outline-section');
                const textarea = section.querySelector('textarea');
                
                // 根据部分类型转换为API需要的名称
                let apiSectionType = '';
                if (sectionType === 'abstract') {
                    apiSectionType = '摘要';
                } else if (sectionType === 'introduction') {
                    apiSectionType = '前言';
                } else if (sectionType === 'progress') {
                    apiSectionType = '研究进展';
                } else if (sectionType === 'conclusion') {
                    apiSectionType = '结论';
                }
                
                // 调用生成API
                if (apiSectionType) {
                    if (apiSectionType === '研究进展') {
                        // 特殊处理研究进展部分，分析次级标题
                        handleResearchProgressSection(section);
                    } else {
                        generateSectionContent(apiSectionType, textarea.value, section);
                    }
                }
            });
        });
    }
    
    // 设置完成综述按钮事件
    function setupCompleteButton(container) {
        const completeButton = container.querySelector('#complete-review-btn');
        if (completeButton) {
            completeButton.addEventListener('click', function() {
                // 收集各部分内容
                const sections = document.querySelectorAll('.outline-section');
                
                // 准备提交数据
                const reviewData = {
                    abstract: '',
                    introduction: '',
                    progress_sections: [],
                    conclusion: ''
                };
                
                sections.forEach(section => {
                    const sectionType = section.getAttribute('data-section-type');
                    const title = section.querySelector('h3').textContent;
                    
                    if (sectionType === 'abstract') {
                // 获取摘要内容
                        const content = section.querySelector('.section-content').innerHTML;
                        reviewData.abstract = content;
                    } else if (sectionType === 'introduction') {
                // 获取前言内容
                        const content = section.querySelector('.section-content').innerHTML;
                        reviewData.introduction = content;
                    } else if (sectionType === 'progress') {
                        // 获取研究进展内容，特殊处理次级标题
                        const subsectionsContainer = section.querySelector('.subsections-container');
                        
                        if (subsectionsContainer) {
                            // 如果已经解析为次级标题
                            const subsectionItems = subsectionsContainer.querySelectorAll('.subsection-item');
                            
                            subsectionItems.forEach(item => {
                                const subsectionTitle = item.querySelector('h4').textContent;
                                const subsectionContent = item.querySelector('.subsection-content').innerHTML;
                                
                                reviewData.progress_sections.push({
                                    title: subsectionTitle,
                                    content: subsectionContent
                                });
                            });
                        } else {
                            // 如果还没有解析次级标题
                            const content = section.querySelector('.section-content').innerHTML;
                            reviewData.progress_sections.push({
                                title: title,
                                content: content
                            });
                        }
                    } else if (sectionType === 'conclusion') {
                        // 获取结论内容
                        const content = section.querySelector('.section-content').innerHTML;
                        reviewData.conclusion = content;
                    }
                });
                
                // 检查是否有研究进展内容
                if (reviewData.progress_sections.length === 0) {
                    showErrorMessage("请先生成研究进展部分内容");
                    return;
                }
                
                // 获取综述标题，如果存在自动标题则使用它
                const autoTitle = window.autoReviewTitle || '综述论文';
                const title = prompt('请输入综述标题:', autoTitle);
                if (!title) return;
                
                // 清除自动标题
                window.autoReviewTitle = null;
                
                // 合并综述
                mergeReviewSections(title, reviewData);
            });
        }
    }
    
    // 生成部分内容
    function generateSectionContent(sectionType, outlineContent, sectionElement) {
        console.log(`开始生成${sectionType}内容...`);
        
        showLoadingMessage(`正在生成${sectionType}内容...`);
        
        fetch('/api/generate-outline-section', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'sid': getSessionId()
            },
            body: JSON.stringify({
                section_type: sectionType,
                outline_content: outlineContent
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showSuccessMessage(`${sectionType}内容生成成功！`);
                
                // 更新部分内容
                if (sectionElement) {
                    const contentElement = sectionElement.querySelector('.section-content');
                    const textarea = sectionElement.querySelector('textarea');
                    
                    if (contentElement) {
                        contentElement.innerHTML = data.content;
                    }
                    
                    if (textarea) {
                        textarea.value = data.content;
                    }
                }
            } else {
                showErrorMessage(`${sectionType}内容生成失败：` + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showErrorMessage(`${sectionType}内容生成时发生错误：` + error.message);
        });
    }

    // 合并综述各部分
    function mergeReviewSections(title, reviewData) {
        console.log('开始合并综述各部分');
        
        // 检查必要的部分是否存在
        if (!reviewData.abstract || !reviewData.introduction || 
            !reviewData.progress_sections.length || !reviewData.conclusion) {
            showErrorMessage("请确保摘要、前言、研究进展和结论部分都已生成");
            return;
        }
        
        showLoadingMessage("正在合并综述各部分...");
        
        fetch('/api/merge-review-sections', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'sid': getSessionId()
            },
            body: JSON.stringify({
                title: title,
                abstract: reviewData.abstract,
                introduction: reviewData.introduction,
                progress_sections: reviewData.progress_sections,
                conclusion: reviewData.conclusion
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showSuccessMessage("综述各部分合并成功");
                
                // 显示下载链接
                const resultContainer = document.createElement('div');
                resultContainer.className = 'card mb-4';
                resultContainer.innerHTML = `
                    <div class="card-header bg-success text-white">
                        <h5 class="mb-0">完整综述已生成</h5>
                    </div>
                    <div class="card-body">
                        <p class="mb-3">综述各部分已成功合并，可以下载完整文档。</p>
                        <a href="${data.word_download_url}" class="btn btn-success mb-3" target="_blank">
                            <i class="fas fa-download"></i> 下载完整综述
                        </a>
                    </div>
                `;
                
                // 添加到页面
                const topicResult = document.getElementById('topic-result');
                if (topicResult) {
                    topicResult.appendChild(resultContainer);
                
                // 滚动到结果区域
                resultContainer.scrollIntoView({ behavior: 'smooth' });
                } else {
                    document.querySelector('.container').appendChild(resultContainer);
                }
            } else {
                showErrorMessage("综述合并失败: " + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showErrorMessage("综述合并过程中发生错误: " + error.message);
        })
        .finally(() => {
            hideLoadingMessage();
        });
    }
});

// 更新进度日志显示
function updateProgressLogDisplay() {
    const logContainer = document.querySelector('.progress-log');
    if (!logContainer) return;
    
    // 清空当前日志
    logContainer.innerHTML = '';
    
    // 添加所有日志条目
    progressLogs.forEach(entry => {
        const logEntry = document.createElement('div');
        logEntry.className = 'progress-log-entry';
        
        const timeSpan = document.createElement('span');
        timeSpan.className = 'progress-log-time';
        timeSpan.textContent = entry.time;
        
        const messageSpan = document.createElement('span');
        messageSpan.className = entry.isError ? 'progress-log-error' : 'progress-log-message';
        messageSpan.textContent = entry.message;
        
        logEntry.appendChild(timeSpan);
        logEntry.appendChild(messageSpan);
        logContainer.appendChild(logEntry);
    });
    
    // 滚动到底部
    logContainer.scrollTop = logContainer.scrollHeight;
}

// 更新进度条
function updateProgressBar(percentage) {
    const progressBar = document.querySelector('.progress-bar');
    const percentageDisplay = document.querySelector('.progress-percentage');
    
    if (progressBar && percentageDisplay) {
        progressBar.style.width = `${percentage}%`;
        percentageDisplay.textContent = `${percentage}%`;
    }
}

// 更新进度消息
function updateProgressMessage(message) {
    const progressMessage = document.querySelector('.progress-message');
    if (progressMessage) {
        progressMessage.textContent = message;
    }
}

// 显示进度容器
function showProgressContainer() {
    const progressContainer = document.getElementById('searchProgress');
    if (progressContainer) {
        progressContainer.style.display = 'block';
    }
}

// 隐藏进度容器
function hideProgressContainer() {
    const progressContainer = document.getElementById('searchProgress');
    if (progressContainer) {
        progressContainer.style.display = 'none';
    }
}

// 重置进度显示
function resetProgress() {
    updateProgressBar(0);
    updateProgressMessage('准备开始搜索...');
    progressLogs = [];
    updateProgressLogDisplay();
}

// 监听搜索进度事件
socket.on('search_progress', function(data) {
    console.log('搜索进度更新:', data);
    
    // 显示进度容器
    showProgressContainer();
    
    // 添加日志
    addProgressLog(data.message, data.stage.includes('error') || data.stage.includes('failed'));
    
    // 更新进度消息
    updateProgressMessage(data.message);
    
    // 如果有百分比信息，更新进度条
    if (data.percentage !== undefined) {
        updateProgressBar(data.percentage);
    }
    
    // 根据不同阶段处理
    switch (data.stage) {
        case 'search_complete':
            // 搜索完成，但保持进度显示
            break;
            
        case 'error':
        case 'search_error':
        case 'search_failed':
            // 显示错误信息
            showToast('error', data.message);
            break;
    }
});

// 执行搜索
async function executeSearch() {
    try {
        const query = document.getElementById('searchInput').value.trim();
        if (!query) {
            showToast('warning', '请输入搜索关键词');
            return;
        }

        // 重置并显示进度
        resetProgress();
        showProgressContainer();
        
        // 显示加载动画
        showLoading();
        
        // 获取筛选条件
        const filters = getFilters();
        
        // 发送搜索请求
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: query,
                filters: filters,
                execute_search: true
            })
        });

        const result = await response.json();
        
        if (result.success) {
            // 保存搜索结果数据，用于后续处理
            window.searchResultData = result;
            console.log('搜索成功，保存结果数据到window.searchResultData', result);
            
            // 显示结果
            displayResults(result.data);
            
            // 显示导出文件链接
            document.getElementById('exportLinks').style.display = 'block';
            document.getElementById('excelLink').href = `/api/download/${result.export_path}`;
            document.getElementById('excelLink').textContent = result.export_path.split('/').pop();
            document.getElementById('reportLink').href = `/api/download/${result.report_path}`;
            document.getElementById('reportLink').textContent = result.report_path.split('/').pop();
            document.getElementById('listLink').href = `/api/download/${result.text_path}`;
            document.getElementById('listLink').textContent = result.text_path.split('/').pop();
            
            showToast('success', `找到 ${result.filtered_count} 篇相关文献，已自动导出并分析`);
            
            // 添加最终完成日志
            addProgressLog(`搜索完成，找到 ${result.filtered_count} 篇相关文献`);
            updateProgressBar(100);
        } else {
            showToast('error', result.error || '搜索失败');
            addProgressLog(`搜索失败: ${result.error || '未知错误'}`, true);
        }
    } catch (error) {
        console.error('搜索出错:', error);
        showToast('error', '搜索过程中出现错误');
        addProgressLog(`搜索出错: ${error.message}`, true);
    } finally {
        hideLoading();
    }
}

// 在导出成功后保存文件路径
function saveExportPath(filePath) {
    localStorage.setItem('lastExportPath', filePath);
}

// 修改现有的导出函数，添加自动分析功能
async function exportToExcel() {
    try {
        showToast('info', '正在导出数据...');
        
        const response = await fetch('/api/export', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                papers: window.searchResults,
                query: document.getElementById('search-input').value
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            saveExportPath(result.data.file_path); // 保存导出文件路径
            
            // 自动开始分析
            showToast('info', '正在分析论文数据...');
            
            const analysisResponse = await fetch('/api/analyze-papers', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    file_path: result.data.file_path
                })
            });
            
            const analysisResult = await analysisResponse.json();
            
            if (analysisResult.success) {
                showToast('success', '导出和分析完成！');
                
                // 更新模态框内容
                document.getElementById('reportContent').textContent = analysisResult.data.report;
                document.getElementById('listContent').textContent = analysisResult.data.text_list;
                
                // 显示模态框
                const modal = new bootstrap.Modal(document.getElementById('analysisModal'));
                modal.show();
            } else {
                showToast('warning', '导出成功，但分析失败：' + analysisResult.error);
            }
        } else {
            showToast('error', '导出失败：' + result.error);
        }
    } catch (error) {
        console.error('导出失败:', error);
        showToast('error', `导出失败: ${error.message}`);
    }
}

// 创建结果容器的辅助函数
function createResultContainer() {
    const container = document.createElement('div');
    container.id = 'review-result-container';
    container.className = 'mt-4';
    document.querySelector('.container').appendChild(container);
    return container;
}

// 复制内容到剪贴板
function copyToClipboard(encodedText) {
    const text = decodeURIComponent(encodedText);
    navigator.clipboard.writeText(text)
        .then(() => {
            showSuccessMessage("内容已复制到剪贴板");
        })
        .catch(err => {
            showErrorMessage("复制失败：" + err);
        });
}

// 在搜索结果页面添加合并综述按钮
function addMergeReviewButton() {
    const reviewSections = {
        abstract: { content: '', element: null },
        introduction: { content: '', element: null },
        progress: { sections: [], elements: [] },
        conclusion: { content: '', element: null }
    };
    
    // 收集已生成的各部分内容
    const reviewContainers = document.querySelectorAll('.review-section-container');
    reviewContainers.forEach(container => {
        const sectionType = container.getAttribute('data-section-type');
        const content = container.querySelector('.review-content').textContent;
        
        if (sectionType === '摘要') {
            reviewSections.abstract.content = content;
            reviewSections.abstract.element = container;
        } else if (sectionType === '前言') {
            reviewSections.introduction.content = content;
            reviewSections.introduction.element = container;
        } else if (sectionType === '结论') {
            reviewSections.conclusion.content = content;
            reviewSections.conclusion.element = container;
        } else {
            // 研究进展部分
            const title = container.querySelector('.section-title').textContent;
            reviewSections.progress.sections.push({
                title: title,
                content: content
            });
            reviewSections.progress.elements.push(container);
        }
    });
    
    // 检查是否有足够的部分可以合并
    const hasAbstract = reviewSections.abstract.content.length > 0;
    const hasIntroduction = reviewSections.introduction.content.length > 0;
    const hasProgress = reviewSections.progress.sections.length > 0;
    const hasConclusion = reviewSections.conclusion.content.length > 0;
    
    // 如果至少有两个部分，添加合并按钮
    if ((hasAbstract && hasIntroduction) || (hasAbstract && hasProgress) || 
        (hasAbstract && hasConclusion) || (hasIntroduction && hasProgress) || 
        (hasIntroduction && hasConclusion) || (hasProgress && hasConclusion)) {
        
        // 查找或创建合并按钮容器
        let mergeButtonContainer = document.getElementById('merge-review-button-container');
        if (!mergeButtonContainer) {
            mergeButtonContainer = document.createElement('div');
            mergeButtonContainer.id = 'merge-review-button-container';
            mergeButtonContainer.className = 'text-center my-4';
            
            // 找到放置按钮的位置
            const outlineContainer = document.querySelector('.outline-container');
            if (outlineContainer) {
                outlineContainer.parentNode.insertBefore(mergeButtonContainer, outlineContainer.nextSibling);
            } else {
                document.querySelector('.container').appendChild(mergeButtonContainer);
            }
        }
        
        // 创建合并按钮
        mergeButtonContainer.innerHTML = `
            <div class="card border-primary">
                <div class="card-body">
                    <h4 class="card-title">合并综述各部分</h4>
                    <p class="card-text">已生成 ${hasAbstract ? '摘要、' : ''}${hasIntroduction ? '前言、' : ''}${hasProgress ? `研究进展(${reviewSections.progress.sections.length}个部分)、` : ''}${hasConclusion ? '结论' : ''}</p>
                    <div class="form-group">
                        <label for="review-title">综述标题</label>
                        <input type="text" class="form-control" id="review-title" placeholder="请输入综述标题">
                    </div>
                    <button id="merge-review-button" class="btn btn-primary btn-lg">
                        <i class="fas fa-object-group"></i> 合并生成完整综述
                    </button>
                </div>
            </div>
        `;
        
        // 添加按钮点击事件
        document.getElementById('merge-review-button').addEventListener('click', function() {
            const title = document.getElementById('review-title').value || '综述论文';
            mergeReviewSections(
                title,
                reviewSections.abstract.content,
                reviewSections.introduction.content,
                reviewSections.progress.sections,
                reviewSections.conclusion.content
            );
        });
    }
}

// 监听DOM变化，当有新的综述部分生成时，添加合并按钮
function setupReviewSectionObserver() {
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length) {
                const addedNode = mutation.addedNodes[0];
                if (addedNode.classList && addedNode.classList.contains('review-section-container')) {
                    // 当添加了新的综述部分时，更新合并按钮
                    addMergeReviewButton();
                }
            }
        });
    });
    
    // 开始观察
    const container = document.querySelector('.container');
    if (container) {
        observer.observe(container, { childList: true, subtree: true });
    }
}

// 页面加载完成后设置观察器
document.addEventListener('DOMContentLoaded', function() {
    setupReviewSectionObserver();
});

// 显示综述部分内容
function displayReviewSection(sectionType, sectionTitle, content) {
    // 创建或获取结果容器
    let resultContainer = document.getElementById('review-results');
    if (!resultContainer) {
        resultContainer = document.createElement('div');
        resultContainer.id = 'review-results';
        resultContainer.className = 'mt-4';
        document.querySelector('.container').appendChild(resultContainer);
    }
    
    // 创建综述部分容器
    const sectionContainer = document.createElement('div');
    sectionContainer.className = 'review-section-container mb-4';
    sectionContainer.setAttribute('data-section-type', sectionType);
    
    // 设置卡片样式
    let headerClass = 'bg-primary';
    if (sectionType === '摘要') {
        headerClass = 'bg-info';
    } else if (sectionType === '前言') {
        headerClass = 'bg-success';
    } else if (sectionType === '结论') {
        headerClass = 'bg-warning';
    }
    
    // 创建卡片内容
    sectionContainer.innerHTML = `
        <div class="card">
            <div class="card-header ${headerClass} text-white">
                <h5 class="mb-0 section-title">${sectionTitle}</h5>
            </div>
            <div class="card-body">
                <div class="review-content markdown-body">${marked.parse(content)}</div>
            </div>
            <div class="card-footer">
                <button class="btn btn-sm btn-outline-primary copy-btn" onclick="copyReviewSection(this)">
                    <i class="far fa-copy"></i> 复制内容
                </button>
                <button class="btn btn-sm btn-outline-secondary edit-btn" onclick="editReviewSection(this)">
                    <i class="far fa-edit"></i> 编辑内容
                </button>
            </div>
        </div>
    `;
    
    // 添加到结果容器
    resultContainer.appendChild(sectionContainer);
    
    // 滚动到新添加的部分
    sectionContainer.scrollIntoView({ behavior: 'smooth' });
    
    // 更新合并按钮
    addMergeReviewButton();
}

// 复制综述部分内容
function copyReviewSection(button) {
    const content = button.closest('.card').querySelector('.review-content').textContent;
    navigator.clipboard.writeText(content)
        .then(() => {
            showSuccessMessage("内容已复制到剪贴板");
        })
        .catch(err => {
            showErrorMessage("复制失败：" + err);
        });
}

// 编辑综述部分内容
function editReviewSection(button) {
    const card = button.closest('.card');
    const contentElement = card.querySelector('.review-content');
    const content = contentElement.textContent;
    
    // 创建编辑区域
    const editArea = document.createElement('div');
    editArea.className = 'edit-area mt-3';
    editArea.innerHTML = `
        <textarea class="form-control" rows="10">${content}</textarea>
        <div class="mt-2">
            <button class="btn btn-primary save-edit-btn">保存</button>
            <button class="btn btn-secondary cancel-edit-btn">取消</button>
        </div>
    `;
    
    // 添加编辑区域
    card.querySelector('.card-body').appendChild(editArea);
    
    // 隐藏原内容和编辑按钮
    contentElement.style.display = 'none';
    button.style.display = 'none';
    
    // 添加保存和取消事件
    editArea.querySelector('.save-edit-btn').addEventListener('click', function() {
        const newContent = editArea.querySelector('textarea').value;
        contentElement.innerHTML = marked.parse(newContent);
        contentElement.style.display = 'block';
        button.style.display = 'inline-block';
        editArea.remove();
        
        // 更新合并按钮
        addMergeReviewButton();
    });
    
    editArea.querySelector('.cancel-edit-btn').addEventListener('click', function() {
        contentElement.style.display = 'block';
        button.style.display = 'inline-block';
        editArea.remove();
    });
}

// 处理大纲部分生成
function handleOutlineSectionGeneration(sectionType, outlineContent) {
    console.log(`开始生成${sectionType}部分内容...`);
    
    showLoadingMessage(`正在生成${sectionType}内容...`);
    
    fetch('/api/generate-outline-section', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'sid': getSessionId()
        },
        body: JSON.stringify({
            section_type: sectionType,
            outline_content: outlineContent
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showSuccessMessage(`${sectionType}内容生成成功！`);
            displayReviewSection(sectionType, sectionType, data.content);
        } else {
            showErrorMessage(`${sectionType}内容生成失败：` + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showErrorMessage(`${sectionType}内容生成时发生错误：` + error.message);
    });
}

// 处理研究进展部分二级标题生成
function handleOutlineSectionReview(sectionTitle, yearStart, yearEnd, maxResults) {
    showLoadingMessage(`正在生成"${sectionTitle}"部分内容，大约需要3-5分钟时间...`);
    showLoading(`正在为"${sectionTitle}"分析相关文献，大约需要3-5分钟时间...`);
    
    fetch('/api/outline-section-review', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'sid': getSessionId()
        },
        body: JSON.stringify({
            section_title: sectionTitle,
            year_start: yearStart,
            year_end: yearEnd,
            max_results: maxResults
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showSuccessMessage(`"${sectionTitle}"部分生成成功！`);
            displayReviewSection('研究进展', sectionTitle, data.content);
        } else {
            showErrorMessage(`"${sectionTitle}"部分生成失败：` + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showErrorMessage(`"${sectionTitle}"部分生成时发生错误：` + error.message);
    });
}

// 生成综述大纲
function generateOutline(titles) {
    showLoadingMessage("正在生成综述大纲...");
    
    fetch('/api/generate-topic', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'sid': getSessionId()
        },
        body: JSON.stringify({
            type: 'outline',
            titles: titles
        })
    })
    .then(response => response.json())
    .then(data => {
        // 调用处理大纲结果的函数
        handleOutlineResult(data);
    })
    .catch(error => {
        console.error('Error:', error);
        showErrorMessage("生成大纲时发生错误：" + error.message);
    });
}

// 显示成功消息
function showSuccessMessage(message) {
    showToast(message, 'success');
}

// 显示错误消息
function showErrorMessage(message) {
    showToast(message, 'error');
}

// 显示加载消息
function showLoadingMessage(message) {
    showToast(message, 'info');
}

// 隐藏加载消息
function hideLoadingMessage() {
    // 可以实现一个隐藏Toast的函数，或者不做任何操作
}

// 处理研究进展次级标题生成
function generateResearchSubsection(subsectionTitle, subsectionContent) {
    console.log(`开始生成研究进展次级标题"${subsectionTitle}"的详细内容...`);
    
    // 检查是否有搜索结果数据
    if (!window.searchResultData || !window.searchResultData.data || window.searchResultData.data.length === 0) {
        showErrorMessage('需要先执行检索获取文献数据');
        return Promise.reject('未找到检索数据');
    }
    
    showLoadingMessage(`正在为"${subsectionTitle}"分析相关文献...`);
    
    return new Promise((resolve, reject) => {
        fetch('/api/generate-research-subsection-content', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'sid': getSessionId()
            },
            body: JSON.stringify({
                subsection_title: subsectionTitle,
                subsection_content: subsectionContent,
                search_papers: window.searchResultData.data,
                related_papers_count: 30  // 相关文献数量，可以根据需要调整
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showSuccessMessage(`"${subsectionTitle}"内容生成成功，基于${data.related_papers_count}篇相关文献`);
                resolve(data.content);
            } else {
                showErrorMessage(`"${subsectionTitle}"内容生成失败：${data.error}`);
                reject(data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showErrorMessage(`生成过程中发生错误: ${error.message}`);
            reject(error);
        });
    });
}

// 处理研究进展部分的解析与生成
function handleResearchProgressSection(section) {
    console.log('开始处理研究进展部分...');
    
    const contentElement = section.querySelector('.section-content');
    const content = contentElement.innerHTML;
    
    // 解析研究进展中的次级标题和内容
    const subsections = parseResearchSubsections(content);
    console.log(`解析出${subsections.length}个次级标题`);
    
    if (subsections.length === 0) {
        showErrorMessage('未能解析出研究进展的次级标题');
        return;
    }
    
    // 创建次级标题处理界面
    const subsectionsContainer = document.createElement('div');
    subsectionsContainer.className = 'subsections-container mt-4';
    
    // 添加一键生成所有内容的按钮
    const generateAllButtonContainer = document.createElement('div');
    generateAllButtonContainer.className = 'text-center mb-4';
    generateAllButtonContainer.innerHTML = `
        <button id="generate-all-subsections" class="btn btn-primary">
            <i class="fas fa-magic"></i> 一键生成所有次级标题内容（约需5-10分钟）
        </button>
    `;
    subsectionsContainer.appendChild(generateAllButtonContainer);
    
    subsections.forEach((subsection, index) => {
        const subsectionElement = document.createElement('div');
        subsectionElement.className = 'subsection-item mb-3';
        subsectionElement.innerHTML = `
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h4 class="mb-0">${subsection.title}</h4>
                    <button class="btn btn-primary btn-sm generate-subsection-btn" data-index="${index}">
                        <i class="fas fa-pen"></i> 生成详细内容
                    </button>
                </div>
                <div class="card-body">
                    <div class="subsection-content">${subsection.content}</div>
                    <div class="subsection-generated-content mt-3" style="display: none;"></div>
                    <div class="text-right mt-2">
                        <button class="btn btn-success btn-sm apply-generated-content" style="display: none;" data-index="${index}">
                            应用生成内容
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        subsectionsContainer.appendChild(subsectionElement);
    });
    
    // 替换原内容
    contentElement.innerHTML = '';
    contentElement.appendChild(subsectionsContainer);
    
    // 添加次级标题生成事件
    setupSubsectionButtons(subsectionsContainer, subsections);
    
    return subsections;
}

// 解析研究进展中的次级标题和内容
function parseResearchSubsections(content) {
    console.log('开始解析研究进展中的次级标题...');
    
    const subsections = [];
    
    // 分割内容为行
    const lines = content.split(/<br\s*\/?>/i);
    console.log(`分割得到${lines.length}行内容`);
    
    // 识别次级标题的正则表达式
    const subsectionRegex = /^(\s*|<p>\s*)(#+\s*|\d+\.\d+\s*|#{3}\s*|\*\*\*\s*)(.*?)(\s*|<\/p>)$/i;
    
    let currentSubsection = null;
    
    // 按行处理内容
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        
        // 检查是否是次级标题
        const match = line.match(subsectionRegex);
        if (match) {
            // 找到新的次级标题
            if (currentSubsection) {
                subsections.push(currentSubsection);
            }
            
            currentSubsection = {
                title: match[3].trim().replace(/^\*+|\*+$/g, ''),  // 移除可能的星号
                content: line + '<br>'
            };
        } else if (currentSubsection) {
            // 将当前行添加到当前次级标题的内容中
            currentSubsection.content += line + '<br>';
        }
    }
    
    // 添加最后一个次级标题
    if (currentSubsection) {
        subsections.push(currentSubsection);
    }
    
    // 如果没有找到次级标题，尝试使用其他方式识别
    if (subsections.length === 0) {
        console.log('未找到标准格式的次级标题，尝试其他识别方式...');
        
        // 尝试根据内容特征识别次级标题
        let inSubsection = false;
        currentSubsection = null;
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();
            if (!line) continue;
            
            // 检查行是否包含数字编号或常见的次级标题特征
            if (line.match(/^(\d+\.\d+|[A-Z]\.\s|\*\*[^*]+\*\*)/)) {
                if (currentSubsection) {
                    subsections.push(currentSubsection);
                }
                
                currentSubsection = {
                    title: line.replace(/^\*+|\*+$/g, '').trim(),
                    content: line + '<br>'
                };
                inSubsection = true;
            } else if (inSubsection && currentSubsection) {
                currentSubsection.content += line + '<br>';
            }
        }
        
        if (currentSubsection) {
            subsections.push(currentSubsection);
        }
    }
    
    console.log(`解析结果: 找到${subsections.length}个次级标题`);
    return subsections;
}

// 设置次级标题按钮的事件处理
function setupSubsectionButtons(container, subsections) {
    // 添加一键生成所有内容按钮事件
    const generateAllButton = container.querySelector('#generate-all-subsections');
    if (generateAllButton) {
        generateAllButton.addEventListener('click', function() {
            // 禁用按钮并显示加载状态
            generateAllButton.disabled = true;
            generateAllButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在生成所有内容...';
            
            // 获取所有生成按钮
            const allGenerateButtons = container.querySelectorAll('.generate-subsection-btn');
            const totalButtons = allGenerateButtons.length;
            
            // 显示提示信息
            showToast(`开始生成${totalButtons}个次级标题的详细内容，请耐心等待`, 'info');
            
            // 使用Promise.all并行处理所有次级标题生成
            const generatePromises = [];
            
            allGenerateButtons.forEach((button, buttonIndex) => {
                const index = parseInt(button.getAttribute('data-index'));
                const subsection = subsections[index];
                const subsectionItem = button.closest('.subsection-item');
                const generatedContent = subsectionItem.querySelector('.subsection-generated-content');
                const applyButton = subsectionItem.querySelector('.apply-generated-content');
                
                // 禁用单个生成按钮
                button.disabled = true;
                button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 等待中...';
                
                // 创建Promise并添加到数组
                const generatePromise = new Promise((resolve, reject) => {
                    // 添加延迟，避免同时发送太多请求
                    setTimeout(() => {
                        // 更新按钮状态
                        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
                        
                        // 调用API生成详细内容
                        generateResearchSubsection(subsection.title, subsection.content)
                            .then(content => {
                                // 显示生成的内容
                                generatedContent.innerHTML = content;
                                generatedContent.style.display = 'block';
                                applyButton.style.display = 'block';
                                
                                // 自动应用生成的内容
                                subsectionItem.querySelector('.subsection-content').innerHTML = content;
                                subsections[index].content = content;
                                
                                // 更新按钮状态
                                button.disabled = false;
                                button.innerHTML = '<i class="fas fa-check"></i> 已生成';
                                button.classList.remove('btn-primary');
                                button.classList.add('btn-success');
                                
                                // 显示进度信息
                                showToast(`已完成 ${buttonIndex + 1}/${totalButtons} 个次级标题的生成`, 'info');
                                
                                resolve();
                            })
                            .catch(error => {
                                console.error('生成详细内容失败:', error);
                                button.disabled = false;
                                button.innerHTML = '<i class="fas fa-exclamation-triangle"></i> 生成失败';
                                button.classList.remove('btn-primary');
                                button.classList.add('btn-danger');
                                reject(error);
                            });
                    }, buttonIndex * 500); // 每个请求间隔500毫秒
                });
                
                generatePromises.push(generatePromise);
            });
            
            // 处理所有生成完成后的操作
            Promise.allSettled(generatePromises)
                .then(results => {
                    const successful = results.filter(r => r.status === 'fulfilled').length;
                    const failed = results.filter(r => r.status === 'rejected').length;
                    
                    // 恢复一键生成按钮状态
                    generateAllButton.disabled = false;
                    generateAllButton.innerHTML = '<i class="fas fa-magic"></i> 重新生成所有内容';
                    
                    // 显示完成消息
                    if (failed === 0) {
                        showSuccessMessage(`所有${totalButtons}个次级标题内容生成完成！`);
                    } else {
                        showToast(`完成${successful}个内容生成，${failed}个生成失败`, 'warning');
                    }
                });
        });
    }
    
    // 添加生成详细内容按钮事件
    const generateButtons = container.querySelectorAll('.generate-subsection-btn');
    generateButtons.forEach(button => {
        button.addEventListener('click', function() {
            const index = parseInt(button.getAttribute('data-index'));
            const subsection = subsections[index];
            const subsectionItem = button.closest('.subsection-item');
            const generatedContent = subsectionItem.querySelector('.subsection-generated-content');
            const applyButton = subsectionItem.querySelector('.apply-generated-content');
            
            // 显示加载状态
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 生成中...';
            
            // 调用API生成详细内容
            generateResearchSubsection(subsection.title, subsection.content)
                .then(content => {
                    // 显示生成的内容
                    generatedContent.innerHTML = content;
                    generatedContent.style.display = 'block';
                    applyButton.style.display = 'block';
                    
                    // 恢复按钮状态
                    button.disabled = false;
                    button.innerHTML = '<i class="fas fa-pen"></i> 重新生成';
                })
                .catch(error => {
                    console.error('生成详细内容失败:', error);
                    // 恢复按钮状态
                    button.disabled = false;
                    button.innerHTML = '<i class="fas fa-pen"></i> 生成详细内容';
                });
        });
    });
    
    // 添加应用生成内容按钮事件
    const applyButtons = container.querySelectorAll('.apply-generated-content');
    applyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const index = parseInt(button.getAttribute('data-index'));
            const subsectionItem = button.closest('.subsection-item');
            const subsectionContent = subsectionItem.querySelector('.subsection-content');
            const generatedContent = subsectionItem.querySelector('.subsection-generated-content');
            
            // 更新次级标题内容
            subsectionContent.innerHTML = generatedContent.innerHTML;
            subsections[index].content = generatedContent.innerHTML;
            
            // 隐藏生成内容和应用按钮
            generatedContent.style.display = 'none';
            button.style.display = 'none';
            
            showSuccessMessage('已应用生成的内容');
        });
    });
} 