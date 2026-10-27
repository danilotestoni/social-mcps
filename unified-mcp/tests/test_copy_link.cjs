const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
let copied='', selected='', denyClipboard=false, denyLegacy=false;
function element(){return {files:[],children:[],setAttribute(){},replaceChildren(...items){this.children=items;},focus(){},select(){selected=this.value;},setSelectionRange(start,end){assert.equal(end-start,this.value.length);}};}
const elements=new Map();
const context=vm.createContext({Map,Promise,URL,Error,JSON,Array,String,Uint8Array,btoa,setTimeout:()=>0,clearTimeout(){}, navigator:{clipboard:{async writeText(text){if(denyClipboard)throw new Error('denied');copied=text;}}}, document:{getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},createElement:element,documentElement:{scrollHeight:700},execCommand(){if(denyLegacy)return false;copied=selected;return true;}},window:{parent:{postMessage(){}},addEventListener(){}}});
vm.runInContext(fs.readFileSync(process.argv[2],'utf8').match(/<script>([\s\S]*?)<\/script>/)[1],context);
const show=vm.runInContext('showResult',context), url='https://example.test/temp-image/'+ 'signed-token-'.repeat(150);
async function test(){
  show(url);const items=elements.get('result').children,field=items[3],button=items[4],notice=items[5];
  assert.equal(field.value,url);assert.equal(field.readOnly,true);
  await button.onclick();assert.equal(copied,url);assert.match(notice.textContent,/copiado/);
  denyClipboard=true;copied='';await button.onclick();assert.equal(copied,url);assert.equal(selected,url);
  denyLegacy=true;await button.onclick();assert.match(notice.textContent,/seleccionado/);assert.equal(selected,url);
  console.log('PASS: complete 1800+ character URL preserved; clipboard, legacy fallback and manual selection verified');
}
test().catch(e=>{console.error(e);process.exitCode=1;});
