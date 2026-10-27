const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {webcrypto} = require('node:crypto');
const html = readFileSync(process.argv[2], 'utf8');
const elements = new Map();
const context = vm.createContext({crypto:webcrypto, Uint8Array, URL, btoa, setTimeout:()=>0, clearTimeout:()=>{}, document:{getElementById:id=>{if(!elements.has(id))elements.set(id,{files:[],replaceChildren(){}});return elements.get(id);}}, window:{parent:{postMessage(){}},addEventListener(){}}, Map, Promise, Error, JSON, Array, String});
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
const upload = vm.runInContext('uploadFile', context);
const data = Buffer.alloc(69168); for(let i=0;i<data.length;i++)data[i]=i%251;
const file = new File([data], 'android.png', {type:'image/png'});
const hash = require('node:crypto').createHash('sha256').update(data).digest('hex');
async function test() {
  let calls=[], chunks=[], failOnce=true, progress=[];
  const call = async (name,args) => {
    calls.push(name);
    if(name==='start_temp_image_upload')return {upload_id:'test-upload'};
    if(name==='upload_temp_image_chunk') {
      if(args.chunk_index===1 && failOnce) {failOnce=false;throw new Error('connection lost');}
      const bytes=Buffer.from(args.chunk_base64,'base64');chunks[args.chunk_index]=bytes;
      assert(bytes.length<=32768);return {chunk_index:args.chunk_index,bytes:bytes.length};
    }
    assert.equal(name,'finish_temp_image_upload');assert.equal(args.expected_sha256,hash);assert.equal(args.auto_optimize,false);
    assert.deepEqual(Buffer.concat(chunks),data);
    return {sha256:hash,size_bytes:data.length,public_url:'https://example.test/image'};
  };
  await assert.rejects(upload(file,call,(n,t)=>progress.push([n,t])), /connection lost/);
  const resume=vm.runInContext('staged',context);assert.equal(resume.next,1);
  const result=await upload(file,call,(n,t)=>progress.push([n,t]),resume);
  assert.equal(result.sha256,hash);assert.equal(calls.filter(x=>x==='start_temp_image_upload').length,1);
  assert.deepEqual(chunks.map(x=>x.length),[32768,32768,3632]);
  assert.equal(progress.at(-1)[0],3);
  await assert.rejects(upload(new File(['bad'],'x.txt',{type:'text/plain'}),call,()=>{}), /JPEG/);
  console.log('PASS: 3 exact chunks, confirmed progress, reconnect resumes without restarting, hash verified, invalid type rejected');
}
test().catch(e=>{console.error(e);process.exitCode=1;});
