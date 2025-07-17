/**
 * 会话管理类
 */
class SessionManager {
    static socketId = null;

    /**
     * 设置Socket.IO会话ID
     * @param {string} id - Socket.IO会话ID
     */
    static setSocketId(id) {
        this.socketId = id;
        localStorage.setItem('socket_id', id);
    }

    /**
     * 获取Socket.IO会话ID
     * @returns {string|null} Socket.IO会话ID
     */
    static getSocketId() {
        if (!this.socketId) {
            this.socketId = localStorage.getItem('socket_id');
        }
        return this.socketId;
    }

    /**
     * 生成随机会话ID
     * @returns {string} 生成的会话ID
     */
    static generateSessionId() {
        return 'sid_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * 获取或创建会话ID
     * @returns {string} 会话ID
     */
    static getOrCreateSessionId() {
        let sid = localStorage.getItem('session_id');
        if (!sid) {
            sid = this.generateSessionId();
            localStorage.setItem('session_id', sid);
        }
        return sid;
    }

    /**
     * 添加会话ID到请求头
     * @param {Object} headers - 请求头对象
     * @returns {Object} 添加了会话ID的请求头对象
     */
    static addSessionIdToHeaders(headers = {}) {
        const socketId = this.getSocketId();
        return {
            ...headers,
            'Content-Type': 'application/json',
            'sid': socketId
        };
    }

    /**
     * 发送搜索请求
     * @param {string} query - 搜索查询
     * @param {string} mode - 搜索模式
     * @param {Object} filters - 过滤条件
     * @returns {Promise<Object>} 搜索结果
     */
    static async sendSearchRequest(query, mode, filters) {
        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: this.addSessionIdToHeaders(),
                body: JSON.stringify({
                    query,
                    mode,
                    filters
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || '搜索请求失败');
            }

            return data;
        } catch (error) {
            console.error('搜索请求错误:', error);
            throw error;
        }
    }

    /**
     * 轮询搜索进度
     * @param {string} searchId - 搜索ID
     * @returns {Promise<Object>} 搜索进度
     */
    static async pollSearchProgress(searchId) {
        try {
            const response = await fetch(`/api/search/progress/${searchId}`, {
                headers: this.addSessionIdToHeaders()
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('进度查询错误:', error);
            throw error;
        }
    }

    /**
     * 导出搜索结果
     * @param {string} exportType - 导出类型
     * @param {Object} data - 导出数据
     * @returns {Promise<Object>} 导出结果
     */
    static async exportResults(exportType, data) {
        try {
            const response = await fetch('/api/export', {
                method: 'POST',
                headers: this.addSessionIdToHeaders(),
                body: JSON.stringify({
                    export_type: exportType,
                    ...data
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || '导出失败');
            }

            return result;
        } catch (error) {
            console.error('导出错误:', error);
            throw error;
        }
    }

    /**
     * 清除会话
     */
    static clearSession() {
        localStorage.removeItem('socket_id');
        this.socketId = null;
    }
} 