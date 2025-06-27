// 读取原始HTML文件内容
const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, 'templates', 'index.html');
let content = fs.readFileSync(filePath, 'utf8');

// 将隐藏的导出按钮样式改为可见
content = content.replace(
  '<div class="d-flex justify-content-end mt-3" style="display: none;">',
  '<div class="d-flex justify-content-end mt-3">'
);

// 替换下载链接，使用正确的API路径
content = content.replace(
  /href="\/api\/download\?file=([^"]+)"/g,
  'href="/api/download/$1"'
);

// 保存修改后的文件
fs.writeFileSync(filePath, content, 'utf8');

console.log('段落模式导出功能修复完成！'); 