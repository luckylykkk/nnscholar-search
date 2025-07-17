/**
 * 异步代表性文章推荐系统
 * 解决页面长时间等待问题
 */

class AsyncRecommendationService {
    constructor() {
        this.taskCheckInterval = 2000; // 每2秒检查一次任务状态
        this.maxWaitTime = 300000; // 最大等待时间5分钟
    }

    /**
     * 启动异步代表性文章推荐
     * @param {string} query - 研究查询
     * @param {string} sessionId - 会话ID
     * @param {string} criteria - 推荐标准
     * @returns {Promise<string>} - 任务ID
     */
    async startRepresentativePapersRecommendation(query, sessionId, criteria = 'impact_and_novelty') {
        try {
            const response = await fetch('/api/async/representative_papers', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'sid': sessionId
                },
                body: JSON.stringify({
                    query: query,
                    criteria: criteria
                })
            });

            const data = await response.json();
            
            if (data.success) {
                return data.task_id;
            } else {
                throw new Error(data.error || '启动任务失败');
            }
        } catch (error) {
            console.error('启动异步推荐失败:', error);
            throw error;
        }
    }

    /**
     * 轮询任务状态
     * @param {string} taskId - 任务ID
     * @param {Function} onProgress - 进度回调
     * @param {Function} onComplete - 完成回调
     * @param {Function} onError - 错误回调
     */
    async pollTaskStatus(taskId, onProgress, onComplete, onError) {
        const startTime = Date.now();
        const maxWaitTime = this.maxWaitTime;

        const checkStatus = async () => {
            try {
                const response = await fetch(`/api/async/task/${taskId}/status`);
                const data = await response.json();

                if (!data.success) {
                    onError(data.error || '获取任务状态失败');
                    return;
                }

                const task = data.task;
                
                switch (task.status) {
                    case 'pending':
                        onProgress(10, '任务排队中...');
                        break;
                    case 'running':
                        onProgress(task.progress || 50, task.message || '正在处理...');
                        break;
                    case 'completed':
                        onComplete(task.result);
                        return;
                    case 'failed':
                        onError(task.error || '任务执行失败');
                        return;
                    case 'expired':
                        onError('任务已过期');
                        return;
                    default:
                        onProgress(0, '未知状态');
                }

                // 检查是否超时
                if (Date.now() - startTime > maxWaitTime) {
                    onError('任务处理超时，请稍后重试');
                    return;
                }

                // 继续轮询
                setTimeout(checkStatus, this.taskCheckInterval);
            } catch (error) {
                console.error('轮询任务状态失败:', error);
                onError('网络错误，请检查连接');
            }
        };

        // 开始轮询
        checkStatus();
    }

    /**
     * 获取任务结果
     * @param {string} taskId - 任务ID
     * @returns {Promise<Object>} - 任务结果
     */
    async getTaskResult(taskId) {
        try {
            const response = await fetch(`/api/async/task/${taskId}/result`);
            const data = await response.json();
            
            if (data.success) {
                return data.result;
            } else {
                throw new Error(data.error || '获取结果失败');
            }
        } catch (error) {
            console.error('获取任务结果失败:', error);
            throw error;
        }
    }

    /**
     * 显示进度指示器
     * @param {HTMLElement} container - 容器元素
     * @param {number} progress - 进度百分比
     * @param {string} message - 进度消息
     */
    showProgress(container, progress, message) {
        const progressHtml = `
            <div class="async-progress-container">
                <div class="progress-info">
                    <div class="progress-message">${message}</div>
                    <div class="progress-bar-container">
                        <div class="progress-bar" style="width: ${progress}%"></div>
                    </div>
                    <div class="progress-percentage">${Math.round(progress)}%</div>
                </div>
                <div class="progress-details">
                    <small class="text-muted">正在为您分析文献，请稍候...</small>
                </div>
            </div>
        `;
        
        container.innerHTML = progressHtml;
    }

    /**
     * 显示推荐结果
     * @param {Object} result - 推荐结果
     * @param {HTMLElement} container - 容器元素
     */
    displayRecommendationResult(result, container) {
        if (!result || !result.content) {
            container.innerHTML = '<div class="alert alert-warning">未能获取推荐结果</div>';
            return;
        }

        const resultHtml = `
            <div class="recommendation-result">
                <div class="result-header">
                    <h4><i class="fas fa-medal text-warning me-2"></i>代表性文章推荐</h4>
                    <p class="text-muted">基于${result.paper_count}篇文献为您精选</p>
                </div>
                <div class="result-content">
                    ${result.content}
                </div>
            </div>
        `;
        
        container.innerHTML = resultHtml;
    }
}

// 全局实例
const asyncRecommendationService = new AsyncRecommendationService();

/**
 * 使用异步方式获取代表性文章推荐
 * @param {string} query - 研究查询
 * @param {string} sessionId - 会话ID
 * @param {HTMLElement} container - 显示结果的容器
 */
async function getRepresentativePapersAsync(query, sessionId, container) {
    try {
        // 显示初始进度
        asyncRecommendationService.showProgress(container, 0, '正在启动推荐任务...');

        // 启动异步任务
        const taskId = await asyncRecommendationService.startRepresentativePapersRecommendation(query, sessionId);
        
        // 开始轮询
        asyncRecommendationService.pollTaskStatus(
            taskId,
            (progress, message) => {
                // 进度更新
                asyncRecommendationService.showProgress(container, progress, message);
            },
            (result) => {
                // 任务完成
                asyncRecommendationService.displayRecommendationResult(result, container);
            },
            (error) => {
                // 任务失败
                container.innerHTML = `<div class="alert alert-danger">推荐失败: ${error}</div>`;
            }
        );

    } catch (error) {
        console.error('异步推荐失败:', error);
        container.innerHTML = `<div class="alert alert-danger">启动推荐失败: ${error.message}</div>`;
    }
}

// 导出到全局
window.AsyncRecommendationService = asyncRecommendationService;
window.getRepresentativePapersAsync = getRepresentativePapersAsync;
