import{f as c}from"./api.DbVY_Eak.js";const a=document.getElementById("leaderboard-tbody"),n=document.getElementById("leaderboard-count-badge"),d=document.getElementById("btn-refresh-leaderboard");async function s(){const e=await c();if(a){if(!e.ok||!e.data||e.data.length===0){a.innerHTML=`
        <tr>
          <td colspan="4" class="px-6 py-8 text-center text-slate-400 font-mono text-xs">
            ${e.ok?"No volunteer records registered yet. Start a native or browser worker to appear here.":"Coordinator is offline. Connect to coordinator to view live rankings."}
          </td>
        </tr>
      `,n&&(n.textContent="0 Volunteers");return}n&&(n.textContent=`${e.data.length} Volunteers`),a.innerHTML=e.data.map((r,l)=>{const t=l+1;let o=`<span class="px-2 py-0.5 rounded-md text-xs font-mono text-slate-400">#${t}</span>`;return t===1?o='<span class="px-2 py-0.5 rounded-md text-xs font-mono font-bold bg-cadmium/15 text-cadmium-light border border-cadmium/30">#1</span>':t===2?o='<span class="px-2 py-0.5 rounded-md text-xs font-mono font-bold bg-surface-elevated text-slate-200 border border-hairline">#2</span>':t===3&&(o='<span class="px-2 py-0.5 rounded-md text-xs font-mono font-bold bg-surface-elevated text-slate-300 border border-hairline">#3</span>'),`
        <tr class="hover:bg-surface-elevated/40 transition-colors border-b border-hairline last:border-b-0">
          <td class="px-4 py-3.5 text-center">${o}</td>
          <td class="px-5 py-3.5 font-mono font-semibold text-slate-100 flex items-center gap-2">
            <span class="w-2 h-2 rounded-md bg-verify shrink-0"></span>
            <span>${i(r.username)}</span>
          </td>
          <td class="px-5 py-3.5 text-right font-mono text-slate-200">${(r.total_attempts??0).toLocaleString()}</td>
          <td class="px-5 py-3.5 text-right font-mono font-bold text-cadmium-light">${(r.records_broken??0).toLocaleString()}</td>
        </tr>
      `}).join("")}}function i(e){return e.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}d&&d.addEventListener("click",s);s();
