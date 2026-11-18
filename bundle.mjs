import {readFile,writeFile} from 'node:fs/promises';
const read=path=>readFile(new URL(path,import.meta.url),'utf8');
const [template,css,model,app,favicon]=await Promise.all(['./dist/index.html','./dist/style.css','./dist/model.mjs','./dist/app.js','./dist/favicon.svg'].map(read));
const source=model.replace(/\bexport\s+(?=(?:const|function)\b)/g,'')+'\n'+app.replace(/^import[^\n]*\n/,'');
if(/<\/script/i.test(source))throw new Error('Embedded source must not contain an HTML script terminator.');
const html=template.replace('<link rel="stylesheet" href="./style.css">',()=>`<style>\n${css}\n</style>`).replace('<script type="module" src="./app.js"></script>',()=>`<script type="module">\n${source}\n</script>`).replace('href="./favicon.svg"',()=>`href="data:image/svg+xml;base64,${Buffer.from(favicon).toString('base64')}"`);
await writeFile(new URL('./index.html',import.meta.url),html);
console.log('Generated self-contained index.html. No external JavaScript or CSS files are required.');
