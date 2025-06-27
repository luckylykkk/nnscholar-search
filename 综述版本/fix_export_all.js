// 读取原始HTML文件内容
const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, 'templates', 'index.html');
let content = fs.readFileSync(filePath, 'utf8');

// 1. 将隐藏的导出按钮样式改为可见
content = content.replace(
  /<div class="d-flex justify-content-end mt-3"( style="display: none;")?>/g,
  '<div class="d-flex justify-content-end mt-3">'
);

// 2. 替换下载链接，使用正确的API路径
content = content.replace(
  /href="\/api\/download\?file=([^"]+)"/g,
  'href="/api/download/$1"'
);

// 3. 在一键检索全部函数中，确保导出按钮的生成代码使用正确的格式
const executeAllPattern = /if \(result\.export_files\) \{[\s\S]+?const exportHtml = `[\s\S]+?<div class="d-flex justify-content-end mt-3".*?>[\s\S]+?<\/div>\s+`;/g;
if (executeAllPattern.test(content)) {
  content = content.replace(executeAllPattern, match => {
    return match.replace(
      /<div class="d-flex justify-content-end mt-3".*?>/,
      '<div class="d-flex justify-content-end mt-3">'
    );
  });
}

// 4. 确保所有地方的导出链接都使用正确的格式
content = content.replace(
  /href="\/api\/download\?file=\${result\.export_files\.([^}]+)}"/g,
  'href="/api/download/${result.export_files.$1}"'
);

// 保存修改后的文件
fs.writeFileSync(filePath, content, 'utf8');

console.log('所有段落模式导出功能修复完成！'); 