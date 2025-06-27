"""
WSGI 入口点文件
这个文件作为 Gunicorn 的入口点，避免 app:app 解析问题
也可以直接运行
"""

import os
import sys
from app import app, socketio

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
