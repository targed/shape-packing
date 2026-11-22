import{f as c}from"./api.BmNrDEVQ.js";const o=document.getElementById("leaderboard-tbody"),n=document.getElementById("leaderboard-count-badge"),d=document.getElementById("btn-refresh-leaderboard");async function l(){const t=await c();if(o){if(!t.ok||!t.data||t.data.length===0){o.innerHTML=`
        <tr>
          <td colspan="4" class="px-6 py-8 text-center text-slate-500">
            ${t.ok?"No volunteer records registered yet. Start a native or browser worker to appear here.":"Coordinator is offline. Connect to coordinator to view live rankings."}
          </td>
        </tr>
      `,n&&(n.textContent="0 Volunteers");return}n&&(n.textContent=`${t.data.length} Volunteers`),o.innerHTML=t.data.map((a,s)=>{const e=s+1;let r=`#${e}`;return e===1?r="#1 (Gold)":e===2?r="#2 (Silver)":e===3&&(r="#3 (Bronze)"),`
        <tr class="hover:bg-slate-800/40 transition-colors">
          <td class="px-4 py-3.5 text-center font-bold text-slate-400">${r}</td>
          <td class="px-5 py-3.5 font-bold text-slate-100 flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
            ${i(a.username)}
          </td>
          <td class="px-5 py-3.5 text-right text-slate-200">${a.total_attempts.toLocaleString()}</td>
          <td class="px-5 py-3.5 text-right font-bold text-amber-300">${a.records_broken.toLocaleString()}</td>
        </tr>
      `}).join("")}}function i(t){return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}d&&d.addEventListener("click",l);l();
