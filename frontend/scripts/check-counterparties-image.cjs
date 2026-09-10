const fs = require('fs');
const path = require('path');

const publicDir = path.join(__dirname, '../public');
const files = fs.readdirSync(publicDir);

console.log('\n===============================================================');
console.log('🔍 ПОИСК КАРТИНКИ КОНТРАГЕНТОВ В public/');
console.log('===============================================================\n');

const matched = files.filter(f => f.toLowerCase().includes('counterpa'));
console.log('Найденные файлы:', matched);

console.log('\n===============================================================\n');
