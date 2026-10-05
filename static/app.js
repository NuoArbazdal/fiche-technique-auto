const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2));

let matchData = [];
let library = [];
const sheetSelections = new Map();

function escapeHtml(value=""){
  return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
}

function getRows(){
  return $$("#rows .plan-row").map(el => ({
    id: el.dataset.id,
    type: el.querySelector(".type").value,
    designation: el.querySelector(".designation").value,
    technical_sheet_id: sheetSelections.get(el.dataset.id) || null,
  }));
}

function addRow(type, designation=""){
  const row = document.createElement("div");
  row.className = "plan-row";
  row.dataset.id = uid();
  row.innerHTML = `
    <div class="row-actions">
      <button class="move-up" title="Monter la ligne">↑</button>
      <button class="move-down" title="Descendre la ligne">↓</button>
    </div>
    <div>
      <select class="type">
        <option ${type==="Titre principal"?"selected":""}>Titre principal</option>
        <option ${type==="Sous-titre"?"selected":""}>Sous-titre</option>
        <option ${type==="FT"?"selected":""}>FT</option>
      </select>
    </div>
    <div><input class="designation" placeholder="Titre ou nom de la fiche technique"></div>
    <div><button class="trash" title="Supprimer la ligne">🗑️</button></div>
  `;

  row.querySelector(".designation").value = designation;

  row.querySelector(".type").addEventListener("change", () => {
    sheetSelections.delete(row.dataset.id);
    clearMatches();
  });
  row.querySelector(".designation").addEventListener("input", () => {
    sheetSelections.delete(row.dataset.id);
    clearMatches();
  });

  row.querySelector(".move-up").addEventListener("click", () => {
    const prev = row.previousElementSibling;
    if(prev){
      row.parentElement.insertBefore(row, prev);
      clearMatches();
    }
  });

  row.querySelector(".move-down").addEventListener("click", () => {
    const next = row.nextElementSibling;
    if(next){
      row.parentElement.insertBefore(next, row);
      clearMatches();
    }
  });

  row.querySelector(".trash").addEventListener("click", () => {
    sheetSelections.delete(row.dataset.id);
    row.remove();
    clearMatches();
  });

  $("#rows").appendChild(row);
  return row;
}

$$("[data-add]").forEach(btn => btn.addEventListener("click", () => {
  const row = addRow(btn.dataset.add);
  clearMatches();
  row.querySelector(".designation").focus();
}));

function clearMatches(){
  matchData = [];
  $("#matchesSection").classList.add("hidden");
  $("#generateZone").classList.add("hidden");
}

$("#searchBtn").addEventListener("click", async () => {
  const active = getRows().filter(r => r.designation.trim());
  if(!active.length){ alert("Ajoute au moins un titre ou une fiche technique."); return; }
  const res = await fetch("/api/match", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({rows:active})
  });
  matchData = await res.json();
  renderMatches();
});

function renderMatches(){
  const box = $("#matches");
  box.innerHTML = "";
  let unresolved = 0;

  for(const item of matchData){
    const row = getRows().find(r => r.id === item.id);
    if(!row) continue;

    if(item.type !== "FT"){
      const d = document.createElement("div");
      d.className = "match-card";
      d.innerHTML = `<strong>${escapeHtml(item.type)}</strong> — ${escapeHtml(item.designation)}`;
      box.appendChild(d);
      continue;
    }

    const d = document.createElement("div");
    d.className = "match-card";
    const candidates = item.candidates || [];

    if(!candidates.length){
      unresolved++;
      d.innerHTML = `
        <strong>FT — ${escapeHtml(item.designation)}</strong>
        <p class="status-bad">Aucune fiche trouvée.</p>
        <input type="file" accept=".pdf,application/pdf" class="missingPdf">
        <button class="secondary uploadMissing">Ajouter cette fiche à la bibliothèque</button>
      `;
      d.querySelector(".uploadMissing").addEventListener("click", async () => {
        const file = d.querySelector(".missingPdf").files[0];
        if(!file){ alert("Choisis le PDF à ajouter."); return; }
        const form = new FormData(); form.append("file", file);
        const r = await fetch("/api/library/import-one",{method:"POST",body:form});
        const result = await r.json();
        if(!r.ok){ alert(result.error || "Import impossible."); return; }
        await refreshLibrary();
        $("#searchBtn").click();
      });
    } else {
      if(!row.technical_sheet_id){
        sheetSelections.set(row.id, candidates[0].id);
        row.technical_sheet_id = candidates[0].id;
      }
      const selected = candidates.find(c => c.id === row.technical_sheet_id) || candidates[0];
      const cls = selected.score >= 90 ? "status-good" : "status-warn";
      d.innerHTML = `
        <strong>FT — ${escapeHtml(item.designation)}</strong>
        <select class="candidateSelect">
          ${candidates.map(c => `<option value="${c.id}" ${c.id===row.technical_sheet_id?"selected":""}>
            ${escapeHtml(c.product_name)}${c.brand?" — "+escapeHtml(c.brand):""} — ${c.score} %
          </option>`).join("")}
        </select>
        <p class="${cls}">Correspondance : ${selected.score} %</p>
      `;
      d.querySelector(".candidateSelect").addEventListener("change", e => {
        sheetSelections.set(row.id, e.target.value);
        renderMatches();
      });
    }
    box.appendChild(d);
  }

  $("#matchesSection").classList.remove("hidden");
  $("#generateZone").classList.toggle("hidden", unresolved > 0);
}

$("#generateBtn").addEventListener("click", async () => {
  const active = getRows().filter(r => r.designation.trim());
  const unresolved = active.filter(r => r.type==="FT" && !r.technical_sheet_id);
  if(unresolved.length){ alert("Certaines FT ne sont pas encore associées."); return; }

  const res = await fetch("/api/generate", {
    method:"POST", headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      filename:$("#pdfFilename").value,
      items:active.map(r => ({
        type:r.type, designation:r.designation, technical_sheet_id:r.technical_sheet_id
      }))
    })
  });
  if(!res.ok){ const e = await res.json().catch(()=>({})); alert(e.error || "Génération impossible."); return; }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = $("#pdfFilename").value || "dossier_fiches_techniques.pdf";
  a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),1000);
});

// Tabs
$$(".tab").forEach(tab => tab.addEventListener("click", () => {
  $$(".tab").forEach(t=>t.classList.remove("active"));
  $$(".tab-panel").forEach(p=>p.classList.remove("active"));
  tab.classList.add("active");
  $("#"+tab.dataset.tab).classList.add("active");
  if(tab.dataset.tab==="library") refreshLibrary();
}));

async function refreshLibrary(){
  const res = await fetch("/api/library");
  library = await res.json();
  populateFilters();
  renderLibrary();
}

function populateFilters(){
  const brands = [...new Set(library.map(x=>x.brand).filter(Boolean))].sort();
  const cats = [...new Set(library.map(x=>x.category).filter(Boolean))].sort();
  const bf=$("#brandFilter"), cf=$("#categoryFilter");
  const bval=bf.value, cval=cf.value;
  bf.innerHTML='<option value="">Toutes les marques</option>'+brands.map(x=>`<option>${escapeHtml(x)}</option>`).join("");
  cf.innerHTML='<option value="">Toutes les catégories</option>'+cats.map(x=>`<option>${escapeHtml(x)}</option>`).join("");
  bf.value=bval; cf.value=cval;
}

function renderLibrary(){
  const q=$("#librarySearch").value.toLowerCase().trim();
  const brand=$("#brandFilter").value, cat=$("#categoryFilter").value;
  const filtered=library.filter(s=>{
    const text=[s.product_name,s.brand,s.reference,s.category,s.original_filename,...(s.aliases||[])].filter(Boolean).join(" ").toLowerCase();
    return (!q||text.includes(q)) && (!brand||s.brand===brand) && (!cat||s.category===cat);
  });

  const box=$("#libraryList"); box.innerHTML="";
  for(const s of filtered){
    const d=document.createElement("details"); d.className="library-card";
    d.innerHTML=`
      <summary><strong>${escapeHtml(s.product_name||s.original_filename)}</strong>${s.brand?" — "+escapeHtml(s.brand):""}</summary>
      <div class="library-edit">
        <input class="product wide" value="${escapeHtml(s.product_name||"")}" placeholder="Nom du produit">
        <input class="brand" value="${escapeHtml(s.brand||"")}" placeholder="Marque">
        <input class="category" value="${escapeHtml(s.category||"")}" placeholder="Catégorie">
        <input class="reference" value="${escapeHtml(s.reference||"")}" placeholder="Référence">
        <input class="version" value="${escapeHtml(s.version_label||"")}" placeholder="Version / date">
        <input class="aliases wide" value="${escapeHtml((s.aliases||[]).join(", "))}" placeholder="Alias">
      </div>
      <div class="library-actions">
        <button class="save">Enregistrer</button>
        <button class="preview">Ouvrir le PDF</button>
        <label class="secondary">Remplacer le PDF <input class="replace" type="file" accept=".pdf" hidden></label>
        <button class="danger">Supprimer</button>
      </div>
    `;
    d.querySelector(".save").onclick=async()=>{
      const payload={
        product_name:d.querySelector(".product").value,
        brand:d.querySelector(".brand").value,
        category:d.querySelector(".category").value,
        reference:d.querySelector(".reference").value,
        version_label:d.querySelector(".version").value,
        aliases:d.querySelector(".aliases").value.split(",").map(x=>x.trim()).filter(Boolean)
      };
      const r=await fetch(`/api/library/${s.id}/metadata`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      if(!r.ok){alert("Modification impossible.");return;} await refreshLibrary();
    };
    d.querySelector(".preview").onclick=()=>window.open(`/api/library/${s.id}/pdf`,"_blank");
    d.querySelector(".replace").onchange=async(e)=>{
      const file=e.target.files[0]; if(!file)return;
      const form=new FormData(); form.append("file",file);
      const r=await fetch(`/api/library/${s.id}/replace`,{method:"POST",body:form});
      if(!r.ok){alert("Remplacement impossible.");return;} await refreshLibrary();
    };
    d.querySelector(".danger").onclick=async()=>{
      if(!confirm(`Supprimer définitivement ${s.product_name||"cette fiche"} ?`))return;
      const r=await fetch(`/api/library/${s.id}`,{method:"DELETE"});
      if(!r.ok){alert("Suppression impossible.");return;} await refreshLibrary();
    };
    box.appendChild(d);
  }
}

["librarySearch","brandFilter","categoryFilter"].forEach(id=>$("#"+id).addEventListener("input",renderLibrary));

$("#importFolderBtn").addEventListener("click", async()=>{
  const files=Array.from($("#folderInput").files).filter(f=>f.name.toLowerCase().endsWith(".pdf"));
  if(!files.length){alert("Sélectionne un dossier contenant des PDF.");return;}
  const progress=$("#importProgress"); progress.innerHTML="";
  let done=0, imported=0, duplicates=0, errors=0;
  for(const file of files){
    const line=document.createElement("div"); line.className="progress-line";
    line.textContent=`${done+1}/${files.length} — ${file.webkitRelativePath||file.name}...`;
    progress.prepend(line);
    const form=new FormData(); form.append("file",file);
    try{
      const r=await fetch("/api/library/import-one",{method:"POST",body:form});
      const result=await r.json();
      if(!r.ok) throw new Error(result.error||"Erreur");
      if(result.status==="duplicate"){duplicates++;line.textContent+=" déjà présent";}
      else{imported++;line.textContent+=" importé";}
    }catch(e){errors++;line.textContent+=" erreur";}
    done++;
  }
  const summary=document.createElement("strong");
  summary.textContent=`${imported} importé(s), ${duplicates} doublon(s), ${errors} erreur(s).`;
  progress.prepend(summary);
  await refreshLibrary();
});

// Tableau volontairement simple : le DOM est la source de vérité.
addRow("Titre principal");
addRow("Sous-titre");
addRow("FT");
