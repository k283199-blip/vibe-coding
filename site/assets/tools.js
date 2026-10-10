"use strict";
(function(){
const both=document.body.dataset.mode==="both";
const input=document.getElementById("url-input"),submit=document.getElementById("convert-button"),clear=document.getElementById("clear-button"),qr=document.getElementById("qr-code"),notice=document.getElementById("notice");
const originalCard=document.getElementById("original-card"),original=document.getElementById("original-link"),shortLink=document.getElementById("short-link"),shortResult=document.getElementById("short-result"),shortPlaceholder=document.getElementById("short-placeholder"),download=document.getElementById("download-qr");
let busy=false, currentUrl="", shortUrl="", pendingRequest=0;
const storageKey="hyuna-short-url-cache-v1";let cache={};
try{cache=JSON.parse(localStorage.getItem(storageKey)||"{}");if(!cache||typeof cache!=="object"||Array.isArray(cache))cache={};}catch(e){cache={};}
function status(message,kind=""){notice.textContent=message;notice.dataset.kind=kind;}
function setBusy(value){busy=value;submit.disabled=value;clear.disabled=value;input.disabled=value;document.getElementById("use-example").disabled=value;submit.textContent=value?"변환 중…":both?"QR + 단축주소 만들기":"QR 코드 만들기";}
function normalize(value){
let text=value.trim();if(!text)throw new Error("변환할 웹 주소를 입력해 주세요.");
if(!/^[a-z][a-z\d+.-]*:/i.test(text))text="https://"+text;
let url;try{url=new URL(text);}catch(e){throw new Error("올바른 웹 주소를 입력해 주세요. 예: https://example.com");}
if(!["https:","http:"].includes(url.protocol))throw new Error("http:// 또는 https:// 웹 주소만 변환할 수 있습니다.");
if(!url.hostname.includes(".")||url.username||url.password)throw new Error("올바른 공개 웹 주소를 입력해 주세요.");
if(new TextEncoder().encode(url.href).length>1800)throw new Error("주소가 너무 깁니다. 1,800바이트 이내의 주소를 입력해 주세요.");
return url.href;
}
function validShort(value){try{const u=new URL(value);return u.protocol==="https:"&&u.hostname==="is.gd"&&/^\/[A-Za-z0-9_]+$/.test(u.pathname);}catch(e){return false;}}
function shorten(url){
if(validShort(cache[url]))return Promise.resolve(cache[url]);
return new Promise((resolve,reject)=>{
const callback="qrnshort_"+Date.now()+"_"+Math.random().toString(36).slice(2);
const script=document.createElement("script");let settled=false;
const timer=setTimeout(()=>finish(new Error("단축 서비스 응답이 늦어지고 있습니다. 잠시 후 다시 눌러 주세요.")),25000);
function finish(error,value){if(settled)return;settled=true;clearTimeout(timer);script.remove();if(error){window[callback]=()=>{};setTimeout(()=>{delete window[callback];},60000);reject(error);}else{delete window[callback];resolve(value);}}
window[callback]=data=>{
if(data&&validShort(data.shorturl)){cache[url]=data.shorturl;try{localStorage.setItem(storageKey,JSON.stringify(cache));}catch(e){}finish(null,data.shorturl);}
else finish(new Error(data&&data.errorcode===3?"단축 서비스 요청 한도에 도달했습니다. 1분 뒤 다시 시도해 주세요.":"단축주소를 만들지 못했습니다. 주소를 확인하고 잠시 후 다시 시도해 주세요."));
};
script.onerror=()=>finish(new Error("단축 서비스에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요."));
script.src="https://is.gd/create.php?format=json&callback="+encodeURIComponent(callback)+"&url="+encodeURIComponent(url);
script.referrerPolicy="no-referrer";document.head.appendChild(script);
});
}
function resetResults(){
qr.innerHTML='<div class="qr-placeholder"><b aria-hidden="true">▣</b><span>QR 코드가 여기에 나타납니다</span></div>';
download.disabled=true;originalCard.hidden=true;shortResult.hidden=true;shortPlaceholder.hidden=false;shortPlaceholder.textContent="변환하면 짧은 주소가 여기에 표시됩니다.";shortLink.removeAttribute("href");shortLink.textContent="";currentUrl="";shortUrl="";document.getElementById("copy-message").textContent="";
}
async function convert(event){
event.preventDefault();if(busy)return;resetResults();
let url;try{url=normalize(input.value);}catch(error){status(error.message,"error");input.focus();return;}
if(typeof QRCode!=="function"){status("QR 생성 기능을 불러오지 못했습니다. 페이지를 새로고침해 주세요.","error");return;}
input.value=url;currentUrl=url;const request=++pendingRequest;setBusy(true);
try{
qr.innerHTML="";new QRCode(qr,{text:url,width:720,height:720,colorDark:"#24243b",colorLight:"#ffffff",correctLevel:QRCode.CorrectLevel.M});
original.textContent=url;original.href=url;originalCard.hidden=false;download.disabled=false;
if(!both){status("QR 코드가 만들어졌습니다. 스캔하거나 이미지로 저장해 보세요.","success");return;}
status("QR 코드가 만들어졌습니다. 단축주소를 생성하고 있습니다.");
const result=await shorten(url);if(request!==pendingRequest)return;shortUrl=result;shortLink.textContent=result;shortLink.href=result;document.getElementById("open-short").href=result;shortResult.hidden=false;shortPlaceholder.hidden=true;
const saved=Math.max(0,url.length-result.length);document.getElementById("saved-count").textContent=saved>0?saved+"글자 더 짧게 공유할 수 있어요.":"이 주소로 간편하게 공유할 수 있어요.";
status("QR 코드와 단축주소가 모두 만들어졌습니다.","success");
}catch(error){
if(both&&originalCard.hidden===false)shortPlaceholder.textContent="단축주소 생성에 실패했습니다. 다시 변환해 주세요.";
status(error.message||"변환하지 못했습니다. 주소를 확인하고 다시 시도해 주세요.","error");
}finally{setBusy(false);}
}
document.getElementById("url-form").addEventListener("submit",convert);
clear.addEventListener("click",()=>{if(busy)return;pendingRequest++;input.value="";resetResults();status("주소를 입력하고 변환 버튼을 눌러 주세요.");input.focus();});
document.getElementById("use-example").addEventListener("click",()=>{input.value=new URL("../",location.href).href;input.focus();});
download.addEventListener("click",()=>{
const canvas=qr.querySelector("canvas");if(!canvas){status("먼저 QR 코드를 만들어 주세요.","error");return;}
const image=document.createElement("canvas");image.width=864;image.height=864;const ctx=image.getContext("2d");ctx.fillStyle="#fff";ctx.fillRect(0,0,864,864);ctx.drawImage(canvas,72,72,720,720);
const link=document.createElement("a");link.href=image.toDataURL("image/png");link.download=both?"QRnShort-QR.png":"URL2QR-QR.png";link.click();
});
if(both)document.getElementById("copy-short").addEventListener("click",async()=>{
if(!shortUrl)return;
try{await navigator.clipboard.writeText(shortUrl);document.getElementById("copy-message").textContent="단축주소가 복사되었습니다.";}
catch(e){document.getElementById("copy-message").textContent="복사 기능을 사용할 수 없습니다. 단축주소를 직접 선택해 복사해 주세요.";}
});
})();
