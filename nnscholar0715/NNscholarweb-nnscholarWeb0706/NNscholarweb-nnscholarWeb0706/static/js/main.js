// 初始化Socket.IO连接
const socket = io();

// 进度日志记录
let progressLogs = [];
const MAX_LOG_ENTRIES = 50;

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
            // 显示结果
            displayResults(result.data);
            
            // 显示导出文件链接
            document.getElementById('exportLinks').style.display = 'block';
            document.getElementById('excelLink').href = `/exports/${result.export_path.split('/').pop()}`;
            document.getElementById('excelLink').textContent = result.export_path.split('/').pop();
            document.getElementById('reportLink').href = `/exports/${result.report_path.split('/').pop()}`;
            document.getElementById('reportLink').textContent = result.report_path.split('/').pop();
            document.getElementById('listLink').href = `/exports/${result.text_path.split('/').pop()}`;
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