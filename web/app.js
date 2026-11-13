import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";
import { SUPABASE_URL, SUPABASE_KEY } from "./config.js";

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);
const $ = (id) => document.getElementById(id);
const app = $("app");
let user = null;
let tab = "home";

// ---------- utilidades (sempre textContent: nunca innerHTML com dados) ----------
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}
function toast(msg, kind = "ok") {
  const t = $("toast");
  t.textContent = msg;
  t.className = `show ${kind}`;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.className = ""), 3500);
}
const fail = (e) => toast(e?.message || String(e), "err");
const del = (table, id, what) => h("button", { class: "ghost", onclick: async () => {
  if (!confirm(`Excluir ${what}?`)) return;
  try { await load(sb.from(table).delete().eq("id", id).select("id")); toast("Excluído."); setTab(tab); } catch (e) { fail(e); }
} }, "Excluir");
const field = (label, input) => h("div", {}, h("label", {}, label), input);
const options = (rows, empty) => [h("option", { value: "" }, empty), ...rows.map((r) => h("option", { value: r.id }, r.name))];

// ---------- autenticacao ----------
function authView() {
  $("top").hidden = true;
  const email = h("input", { type: "email", placeholder: "email", autocomplete: "email" });
  const pass = h("input", { type: "password", placeholder: "senha (min. 8)", autocomplete: "current-password" });
  const run = (mode) => async () => {
    try {
      const fn = mode === "in" ? sb.auth.signInWithPassword : sb.auth.signUp;
      const { data, error } = await fn.call(sb.auth, { email: email.value.trim(), password: pass.value });
      if (error) throw error;
      if (mode === "up" && !data.session) toast("Conta criada. Confirme o email e entre.");
    } catch (e) { fail(e); }
  };
  app.replaceChildren(h("div", { class: "card auth" },
    h("h2", {}, "DarkStudio AI"), h("p", { class: "mut" }, "Entre para criar vídeos para seus canais."),
    field("Email", email), field("Senha", pass),
    h("div", { class: "row" },
      h("button", { class: "pri", onclick: run("in") }, "Entrar"),
      h("button", { class: "ghost", style: "margin-top:14px", onclick: run("up") }, "Criar conta"))));
}

// ---------- dados ----------
const load = async (q) => { const { data, error } = await q; if (error) throw error; return data; };
const voices = () => load(sb.from("voice_profiles").select("id,name,engine,category").order("name"));
const niches = () => load(sb.from("niche_presets").select("id,name,visual_style,default_voice_id").order("name"));
const channels = () => load(sb.from("channels").select("id,name,tone,audience,niche_preset_id,default_voice_id").order("name"));

// ---------- telas ----------
const STEP = { split_scenes: "Dividindo em cenas", generate_image: "Gerando imagens", generate_audio: "Gerando narração", build_subtitles: "Legendas", render_clip: "Montando cenas", render_final: "Renderizando vídeo", upload: "Enviando", approve_storyboard: "Aguardando sua revisão do storyboard" };
const STATUS_PT = { draft: "rascunho", scripting: "roteiro", storyboard: "storyboard", producing: "produzindo", rendering: "renderizando", awaiting_approval: "aguardando aprovação", completed: "concluído", failed: "falhou" };
let poll = null;
const openScenes = new Set();
const signed = new Map(); // storage_key -> { url, exp }
async function signUrls(keys) {
  const need = keys.filter((k) => !signed.has(k) || signed.get(k).exp < Date.now());
  if (need.length) {
    const { data } = await sb.storage.from("media").createSignedUrls(need, 3600);
    for (const d of data ?? []) if (d.signedUrl) signed.set(d.path, { url: d.signedUrl, exp: Date.now() + 3300_000 });
  }
}
const autoQueued = new Set(); // projetos cuja geracao pendente ja foi enfileirada automaticamente nesta sessao
async function enqueueMissing(projectId, sc) {
  const mk = (x, type, pre) => ({ user_id: user.id, project_id: projectId, type, status: "QUEUED", payload: { scene_id: x.id }, idempotency_key: `${pre}:${x.id}` });
  const rows = [...sc.filter((x) => !x.image).map((x) => mk(x, "generate_image", "img")), ...sc.filter((x) => !x.audio_asset_id).map((x) => mk(x, "generate_audio", "aud"))];
  if (!rows.length) return 0;
  const { error } = await sb.from("tasks").upsert(rows, { onConflict: "user_id,idempotency_key", ignoreDuplicates: true });
  if (error) throw error;
  return rows.length;
}
const autoOpened = new Set(); // projetos cujas cenas ja foram abertas automaticamente (o usuario pode fechar)

function progressOf(allTasks) {
  const tasks = allTasks.filter((t) => t.type !== "approve_storyboard"); // etapa antiga, nao usada mais
  const total = tasks.length;
  const done = tasks.filter((t) => t.status === "COMPLETED").length;
  const failed = tasks.some((t) => t.status === "FAILED");
  const running = tasks.find((t) => t.status === "RUNNING") ?? tasks.find((t) => ["QUEUED", "WAITING_PROVIDER", "PENDING", "WAITING_APPROVAL"].includes(t.status));
  const pct = total ? Math.round((done / total) * 100) : 0;
  let label = "Sem tarefas";
  if (total) label = failed ? "Falhou" : done === total ? "Concluído" : running ? (STEP[running.type] ?? running.type) + (running.status === "RUNNING" ? "…" : (running.status === "WAITING_APPROVAL" ? "" : " (na fila)")) : "Aguardando";
  return { pct, label, failed, done, total };
}

// capas (kind=thumbnail) por projeto: { project_id -> { key, url } }
async function thumbsFor(projectIds) {
  const ids = [...new Set(projectIds)].filter(Boolean);
  if (!ids.length) return new Map();
  const rows = await load(sb.from("media_assets").select("project_id,storage_key").eq("kind", "thumbnail").in("project_id", ids).order("created_at", { ascending: false }));
  const m = new Map();
  for (const r of rows) if (!m.has(r.project_id)) m.set(r.project_id, { key: r.storage_key });
  await signUrls([...m.values()].map((v) => v.key));
  for (const v of m.values()) v.url = signed.get(v.key)?.url;
  return m;
}
const capaImg = (t, cls = "capa") => (t?.url ? h("img", { class: cls, src: t.url, alt: "Capa do vídeo", loading: "lazy" }) : null);

async function viewHome() {
  const count = async (table) => { const { count: n, error } = await sb.from(table).select("id", { count: "exact", head: true }); if (error) throw error; return n ?? 0; };
  const [nProj, nReady, nMusic, nVoice, recent] = await Promise.all([count("projects"), count("project_exports"), count("music_assets"), count("voice_profiles"),
    load(sb.from("projects").select("id,title,status,created_at").order("created_at", { ascending: false }).limit(4))]);
  const caps = await thumbsFor(recent.map((p) => p.id)).catch(() => new Map());
  const go = (t) => () => setTab(t);
  const stat = (ic, n, label, t) => h("div", { class: "stat", style: "cursor:pointer", onclick: go(t) }, h("span", { class: "ic" }, ic), h("div", {}, h("b", {}, String(n)), h("span", { class: "mut" }, label)));
  const pill = (st) => h("span", { class: `pill ${st === "awaiting_approval" || st === "completed" ? "ok" : st === "failed" ? "bad" : "run"}` }, st === "awaiting_approval" ? "pronto" : (STATUS_PT[st] ?? st));
  const quick = (ic, t, sub, tab2) => h("button", { onclick: go(tab2) }, h("span", { style: "font-size:20px" }, ic), h("strong", {}, t), h("span", { class: "mut" }, sub));
  app.replaceChildren(
    h("div", { class: "hero" }, h("h1", {}, "Transforme suas ideias em ", h("em", {}, "vídeos incríveis!")),
      h("p", {}, "Cole o roteiro, escolha canal, voz e música, e o DarkStudio gera o documentário completo."),
      h("button", { class: "pri", style: "margin:0", onclick: go("new") }, "🚀 Criar novo projeto →")),
    h("div", { class: "stats" }, stat("📁", nProj, "Projetos criados", "projects"), stat("🎬", nReady, "Vídeos prontos", "ready"), stat("🎵", nMusic, "Músicas na biblioteca", "music"), stat("🎙", nVoice, "Vozes de IA", "voices")),
    h("div", { class: "cols" },
      h("div", { class: "card" }, h("div", { class: "row", style: "justify-content:space-between;align-items:center;margin-bottom:6px" }, h("h2", { style: "margin:0;flex:none;min-width:0" }, "Seus projetos recentes"), h("a", { href: "#", style: "color:var(--ac);flex:none;min-width:0", onclick: (e) => { e.preventDefault(); setTab("projects"); } }, "Ver todos →")),
        recent.length ? recent.map((p) => h("div", { class: "proj" }, capaImg(caps.get(p.id), "capa sm") ?? h("div", { class: "av" }, (p.title || "?").trim().charAt(0).toUpperCase()),
          h("div", {}, h("strong", {}, p.title), h("span", { class: "mut" }, new Date(p.created_at).toLocaleString("pt-BR"))), pill(p.status),
          p.status === "awaiting_approval" ? h("button", { class: "ghost", onclick: go("ready") }, "Baixar") : h("button", { class: "ghost", onclick: go("projects") }, "Ver")))
          : h("p", { class: "mut" }, "Nenhum projeto ainda. Clique em “Criar novo projeto”.")),
      h("div", { class: "card" }, h("h2", {}, "⚡ Acesso rápido"), h("div", { class: "quick" },
        quick("🎞", "Novo projeto", "Comece a criar", "new"), quick("🎵", "Músicas", "Explore a biblioteca", "music"),
        quick("🎙", "Vozes", "Ouça as vozes", "voices"), quick("📡", "Canais", "Gerencie seus canais", "channels")))));
}

async function viewProjects() {
  clearInterval(poll);
  const draw = async () => {
    const [rows, tasks] = await Promise.all([
      load(sb.from("projects").select("id,title,status,created_at,channels(name)").is("deleted_at", null).order("created_at", { ascending: false })),
      load(sb.from("tasks").select("project_id,type,status,last_error")),
    ]);
    const byProj = new Map();
    for (const t of tasks) (byProj.get(t.project_id) ?? byProj.set(t.project_id, []).get(t.project_id)).push(t);
    for (const [pid, ts] of byProj) {
      if (!autoOpened.has(pid) && ts.some((t) => t.type === "split_scenes" && t.status === "COMPLETED")) { autoOpened.add(pid); openScenes.add(pid); }
    }
    const scenes = new Map();
    for (const id of openScenes) scenes.set(id, await load(sb.from("scenes").select("id,user_id,position,narration_text,image_prompt,est_duration_s,duration_s,audio_asset_id,image:media_assets!image_asset_id(storage_key)").eq("project_id", id).is("deleted_at", null).order("position")));
    for (const [pid, sc] of scenes) {
      const ts = byProj.get(pid) ?? [];
      const active = ts.some((t) => ["generate_image", "generate_audio"].includes(t.type) && !["COMPLETED", "FAILED", "CANCELLED"].includes(t.status));
      if (!autoQueued.has(pid) && !active && sc.some((x) => !x.image || !x.audio_asset_id)) {
        autoQueued.add(pid);
        enqueueMissing(pid, sc).then((n) => n && toast("Geração de imagens e narração enfileirada automaticamente.")).catch(() => autoQueued.delete(pid));
      }
    }
    await signUrls([...scenes.values()].flat().map((x) => x.image?.storage_key).filter(Boolean)).catch(() => {});
    app.replaceChildren(h("div", { class: "plist" }, h("h2", {}, "Projetos"),
      rows.length ? rows.map((p) => {
        const pr = progressOf(byProj.get(p.id) ?? []);
        const sc = scenes.get(p.id);
        const done = p.status === "awaiting_approval" || p.status === "completed";
        return h("section", { class: `pcard${pr.failed ? " bad" : done ? " ok" : ""}` },
          h("div", { class: "phead" },
            h("div", { class: "av" }, (p.title || "?").trim().charAt(0).toUpperCase()),
            h("div", { class: "ptitle" }, h("strong", {}, p.title), h("div", { class: "mut" }, `${p.channels?.name ?? "—"} · ${new Date(p.created_at).toLocaleString("pt-BR")}`)),
            h("span", { class: `pill ${pr.failed ? "bad" : done ? "ok" : "run"}` }, pr.failed ? "falhou" : done ? "pronto" : (STATUS_PT[p.status] ?? p.status))),
          h("div", { class: "pbody" },
          h("div", {},
            h("div", { class: `bar${pr.failed ? " bad" : ""}` }, h("div", { style: `width:${pr.pct}%` })),
            h("div", { class: "mut" }, `${pr.label} · ${pr.pct}%${pr.total ? ` (${pr.done}/${pr.total} etapas)` : ""}`),
            pr.failed ? h("div", { class: "mut", style: "color:var(--err)" }, `Erro: ${(byProj.get(p.id) ?? []).find((t) => t.status === "FAILED")?.last_error ?? "desconhecido"}`) : null),
          p.status === "awaiting_approval" ? h("div", { class: "ready" }, "✅ Vídeo pronto! Baixe na aba ",
            h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); setTab("ready"); } }, "Vídeos prontos"), ".") : null,
          h("div", { class: "pactions" },
            h("button", { class: "ghost", style: "flex:none;min-width:0", onclick: () => { openScenes.has(p.id) ? openScenes.delete(p.id) : openScenes.add(p.id); viewProjects().catch(fail); } }, sc ? "Ocultar cenas" : "Ver cenas"),
            pr.failed ? h("button", { class: "ghost", style: "flex:none;min-width:0", onclick: async (ev) => {
              ev.target.disabled = true;
              try { const { data, error } = await sb.rpc("retry_failed_tasks", { p_project: p.id }); if (error) throw error; toast(`${data} tarefa(s) devolvida(s) à fila.`); viewProjects().catch(fail); } catch (e) { fail(e); ev.target.disabled = false; }
            } }, "Tentar de novo as que falharam") : null),
          sc ? h("div", { class: "scenes" }, sc.length ? sc.map((x) => h("div", { class: "scene" },
            x.image && signed.get(x.image.storage_key) ? h("img", { src: signed.get(x.image.storage_key).url, loading: "lazy", class: "thumb", alt: "" }) : h("div", { class: "thumb ph" }, x.image ? "…" : "sem imagem"),
            h("div", {}, h("div", {}, `${x.position}. ${x.narration_text}`), h("div", { class: "mut" }, `🎨 ${x.image_prompt} · ${x.duration_s ? `🔊 ${x.duration_s}s` : `~${x.est_duration_s}s`}`)))) : h("p", { class: "mut" }, "Ainda sem cenas.")) : null));
      }) : h("p", { class: "mut" }, "Nenhum projeto ainda. Crie o primeiro em “Novo projeto”.")));
  };
  await draw();
  poll = setInterval(() => { if (tab === "projects" && !document.hidden) draw().catch(() => {}); }, 3000);
}

async function viewNew() {
  const [chs, nis, vs] = await Promise.all([channels(), niches(), voices()]);
  if (!chs.length) { app.replaceChildren(h("div", { class: "card" }, h("p", {}, "Cadastre um canal primeiro, na aba Canais."))); return; }
  const title = h("input", { placeholder: "Título do vídeo" });
  const ch = h("select", {}, options(chs, "Escolha o canal").slice(1));
  const voice = h("select", {}, options(vs, "Voz padrão do canal"));
  const musics = await load(sb.from("music_assets").select("id,name").order("name"));
  const music = h("select", {}, h("option", { value: "" }, "Música: automática (sorteia da biblioteca)"), h("option", { value: "none" }, "Sem música"), ...musics.map((m) => h("option", { value: m.id }, m.name)));
  const script = h("textarea", { placeholder: "Cole aqui o roteiro / narração completa…" });
  const btn = h("button", { class: "pri" }, "Criar projeto e iniciar");
  const KEY = `ds_draft_${user.id}`;
  const saveDraft = () => { try { localStorage.setItem(KEY, JSON.stringify({ t: title.value, c: ch.value, v: voice.value, s: script.value })); } catch {} };
  try {
    const d = JSON.parse(localStorage.getItem(KEY) || "null");
    if (d) { title.value = d.t ?? ""; script.value = d.s ?? ""; if (chs.some((x) => x.id === d.c)) ch.value = d.c; if (vs.some((x) => x.id === d.v)) voice.value = d.v; }
  } catch {}
  for (const el of [title, ch, voice, script]) { el.addEventListener("input", saveDraft); el.addEventListener("change", saveDraft); }
  btn.addEventListener("click", async () => {
    try {
      if (!title.value.trim() || !script.value.trim()) throw new Error("Preencha título e roteiro.");
      btn.disabled = true;
      const c = chs.find((x) => x.id === ch.value);
      const niche = nis.find((n) => n.id === c.niche_preset_id);
      const voiceId = voice.value || c.default_voice_id || niche?.default_voice_id || null;
      const [proj] = await load(sb.from("projects").insert({ user_id: user.id, channel_id: c.id, title: title.value.trim(), input_mode: "script", visual_style: niche?.visual_style ?? null, voice_id: voiceId, music_enabled: music.value !== "none", music_id: music.value && music.value !== "none" ? music.value : null, status: "scripting" }).select("id"));
      const [sc] = await load(sb.from("scripts").insert({ user_id: user.id, project_id: proj.id }).select("id"));
      const [ver] = await load(sb.from("script_versions").insert({ user_id: user.id, script_id: sc.id, version: 1, content: script.value, source: "pasted" }).select("id"));
      await load(sb.from("scripts").update({ current_version_id: ver.id }).eq("id", sc.id).select("id"));
      await load(sb.from("tasks").insert({ user_id: user.id, project_id: proj.id, type: "split_scenes", status: "QUEUED", payload: { script_version_id: ver.id, voice_id: voiceId }, idempotency_key: `split:${ver.id}` }).select("id"));
      try { localStorage.removeItem(KEY); } catch {}
      toast("Projeto criado. A divisão em cenas entrou na fila.");
      setTab("projects");
    } catch (e) { fail(e); btn.disabled = false; }
  });
  app.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Novo projeto"),
    field("Título", title),
    h("div", { class: "row" }, field("Canal", ch), h("div", {}, h("label", {}, "Voz (opcional)"), h("div", { class: "row", style: "gap:8px;flex-wrap:nowrap" }, voice, previewButton(() => voice.value || chs.find((x) => x.id === ch.value)?.default_voice_id || nis.find((n) => n.id === chs.find((x) => x.id === ch.value)?.niche_preset_id)?.default_voice_id)))), field("Música de fundo", music),
    field("Roteiro / narração", script), btn));
}

async function viewChannels() {
  const [chs, nis, vs] = await Promise.all([channels(), niches(), voices()]);
  const nName = h("input", { placeholder: "Ex.: Mistérios e casos reais" });
  const nStyle = h("input", { placeholder: "Estilo visual (ex.: dark cinematic documentary, fog, low light)" });
  const nVoice = h("select", {}, options(vs, "Voz padrão do nicho"));
  const addNiche = h("button", { class: "pri" }, "Salvar nicho");
  addNiche.addEventListener("click", async () => {
    if (addNiche.disabled) return;
    addNiche.disabled = true;
    try {
      if (!nName.value.trim()) throw new Error("Dê um nome ao nicho.");
      await load(sb.from("niche_presets").insert({ user_id: user.id, name: nName.value.trim(), visual_style: nStyle.value.trim() || null, default_voice_id: nVoice.value || null }).select("id"));
      toast("Nicho salvo."); viewChannels().catch(fail);
    } catch (e) { fail(e); addNiche.disabled = false; }
  });
  const cName = h("input", { placeholder: "Nome do canal" });
  const cTone = h("input", { placeholder: "Tom (ex.: sério, misterioso)" });
  const cAud = h("input", { placeholder: "Público (ex.: adultos 25-45, Brasil)" });
  const cNiche = h("select", {}, options(nis, "Nicho"));
  const cVoice = h("select", {}, options(vs, "Voz padrão do canal"));
  const addCh = h("button", { class: "pri" }, "Salvar canal");
  addCh.addEventListener("click", async () => {
    if (addCh.disabled) return;
    addCh.disabled = true;
    try {
      if (!cName.value.trim()) throw new Error("Dê um nome ao canal.");
      await load(sb.from("channels").insert({ user_id: user.id, name: cName.value.trim(), tone: cTone.value.trim() || null, audience: cAud.value.trim() || null, niche_preset_id: cNiche.value || null, default_voice_id: cVoice.value || null }).select("id"));
      toast("Canal salvo."); viewChannels().catch(fail);
    } catch (e) { fail(e); addCh.disabled = false; }
  });
  app.replaceChildren(
    h("div", { class: "card" }, h("h2", {}, "Canais"),
      chs.length ? chs.map((c) => h("div", { class: "item" }, h("div", {}, h("strong", {}, c.name), h("div", { class: "mut" }, [c.tone, c.audience].filter(Boolean).join(" · ") || "—")),
        h("span", { class: "tag" }, nis.find((n) => n.id === c.niche_preset_id)?.name ?? "sem nicho"), del("channels", c.id, `o canal “${c.name}”`))) : h("p", { class: "mut" }, "Nenhum canal."),
      h("h3", { style: "margin-top:18px" }, "Novo canal"), field("Nome", cName),
      h("div", { class: "row" }, field("Nicho", cNiche), field("Voz", cVoice)),
      h("div", { class: "row" }, field("Tom", cTone), field("Público", cAud)), addCh),
    h("div", { class: "card" }, h("h2", {}, "Nichos"),
      nis.length ? nis.map((n) => h("div", { class: "item" }, h("div", {}, h("strong", {}, n.name), h("div", { class: "mut" }, n.visual_style || "sem estilo definido")), del("niche_presets", n.id, `o nicho “${n.name}”`))) : h("p", { class: "mut" }, "Nenhum nicho."),
      h("h3", { style: "margin-top:18px" }, "Novo nicho"), field("Nome", nName), field("Estilo visual", nStyle), field("Voz padrão", nVoice), addNiche));
}

// Pré-escuta de voz: usa a amostra guardada; se não existir, pede ao worker (até ~2 min na 1ª vez) e toca quando ficar pronta.
const previewKey = (vid) => `${user.id}/voices/${vid}.wav`;
async function previewUrl(vid) {
  const { data, error } = await sb.storage.from("media").createSignedUrl(previewKey(vid), 3600);
  return error ? null : data.signedUrl;
}
async function requestPreview(vid) {
  const key = `vprev:${vid}`;
  const [t] = await load(sb.from("tasks").select("id,status").eq("idempotency_key", key));
  if (!t) await load(sb.from("tasks").upsert({ user_id: user.id, type: "voice_preview", status: "QUEUED", priority: 10, payload: { voice_id: vid }, idempotency_key: key, timeout_s: 600 }, { onConflict: "user_id,idempotency_key", ignoreDuplicates: true }).select("id"));
  else if (t.status === "FAILED" || t.status === "COMPLETED") await load(sb.from("tasks").update({ status: "QUEUED", attempts: 0, run_after: new Date().toISOString(), last_error: null }).eq("id", t.id).select("id"));
}
let nowPlaying = null;
function previewButton(getVoiceId, label = "▶ Ouvir") {
  const btn = h("button", { class: "ghost", type: "button", style: "flex:none;min-width:0" }, label);
  btn.addEventListener("click", async () => {
    const vid = getVoiceId();
    if (!vid) { toast("Escolha uma voz para ouvir (ou use a padrão do canal).", "err"); return; }
    btn.disabled = true;
    try {
      let url = await previewUrl(vid);
      if (!url) {
        await requestPreview(vid);
        for (let i = 0; i < 60 && !url; i++) {
          btn.textContent = "Gerando amostra… (pode levar 2 min)";
          await new Promise((r) => setTimeout(r, 5000));
          url = await previewUrl(vid);
          if (i % 6 === 5) { const [t] = await load(sb.from("tasks").select("status,last_error").eq("idempotency_key", `vprev:${vid}`)); if (t?.status === "FAILED") throw new Error(`Amostra falhou: ${t.last_error ?? "erro"}`); }
        }
        if (!url) throw new Error("A amostra demorou demais. Tente de novo em instantes.");
      }
      nowPlaying?.pause();
      nowPlaying = new Audio(url);
      await nowPlaying.play();
    } catch (e) { fail(e); }
    btn.textContent = label; btn.disabled = false;
  });
  return btn;
}

async function viewVoices() {
  const rows = await load(sb.from("voice_profiles").select("id,name,engine,category,license").order("name"));
  app.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Vozes"), h("p", { class: "mut" }, "Clique em Ouvir para escutar uma amostra. Na primeira vez ela é gerada (até 2 min) e fica guardada."),
    rows.length ? rows.map((v) => h("div", { class: "item" }, h("div", {}, h("strong", {}, v.name), h("div", { class: "mut" }, `${v.engine} · ${v.category ?? ""} · ${v.license}`)), previewButton(() => v.id))) : h("p", { class: "mut" }, "Nenhuma voz. Rode a migration 0002 no Supabase.")));
}

function musicPlay(m) {
  return h("button", { class: "ghost", type: "button", onclick: async (ev) => {
    ev.target.disabled = true;
    try {
      await signUrls([m.storage_key]);
      const u = signed.get(m.storage_key)?.url;
      if (!u) throw new Error("Não consegui abrir a música.");
      nowPlaying?.pause(); nowPlaying = new Audio(u); await nowPlaying.play();
    } catch (e) { fail(e); }
    ev.target.disabled = false;
  } }, "▶ Ouvir");
}

async function viewMusic() {
  const rows = await load(sb.from("music_assets").select("id,name,category,license,origin_url,storage_key,bytes").order("created_at", { ascending: false }));
  const file = h("input", { type: "file", accept: "audio/mpeg,audio/mp3,audio/wav,audio/ogg,audio/mp4,.mp3,.wav,.ogg,.m4a" });
  const name = h("input", { placeholder: "Nome da música (ex.: Dark Ambient 1)" });
  const mood = h("input", { placeholder: "Clima (ex.: sombrio, suspense, calmo)" });
  const lic = h("input", { placeholder: "Licença (ex.: Pixabay, CC0, YouTube Audio Library)" });
  const src = h("input", { placeholder: "Link de onde baixou" });
  const btn = h("button", { class: "pri" }, "Enviar música");
  btn.addEventListener("click", async () => {
    try {
      const f = file.files[0];
      if (!f || !name.value.trim() || !lic.value.trim() || !src.value.trim()) throw new Error("Escolha o arquivo e preencha nome, licença e link.");
      if (f.size > 50 * 1024 * 1024) throw new Error("Arquivo maior que 50 MB.");
      btn.disabled = true;
      const ext = (f.name.split(".").pop() || "mp3").toLowerCase().replace(/[^a-z0-9]/g, "");
      const key = `${user.id}/music/${crypto.randomUUID()}.${ext}`;
      const up = await sb.storage.from("media").upload(key, f, { contentType: f.type || "audio/mpeg" });
      if (up.error) throw up.error;
      await load(sb.from("music_assets").insert({ user_id: user.id, name: name.value.trim(), category: mood.value.trim() || null, license: lic.value.trim(), origin_url: src.value.trim(), storage_key: key, bytes: f.size }).select("id"));
      toast("Música enviada."); setTab("music");
    } catch (e) { fail(e); btn.disabled = false; }
  });
  const delMusic = (m) => h("button", { class: "ghost", onclick: async () => {
    if (!confirm(`Excluir a música “${m.name}”?`)) return;
    try {
      if (m.storage_key) await sb.storage.from("media").remove([m.storage_key]);
      await load(sb.from("music_assets").delete().eq("id", m.id).select("id")); toast("Excluída."); setTab("music");
    } catch (e) { fail(e); }
  } }, "Excluir");
  app.replaceChildren(
    h("div", { class: "card" }, h("h2", {}, "Músicas de fundo"),
      h("p", { class: "mut" }, "Envie só faixas que você pode usar em vídeo monetizado (Pixabay Music, YouTube Audio Library, CC0…). Em cada vídeo a música toca baixinho, abaixa quando há narração e some no final."),
      rows.length ? rows.map((m) => h("div", { class: "item" }, h("div", {}, h("strong", {}, m.name), h("div", { class: "mut" }, `${m.category ?? "sem clima"} · ${m.license} · ${m.bytes ? (m.bytes / 1048576).toFixed(1) + " MB" : ""}`)), h("div", { class: "row", style: "gap:8px;flex-wrap:nowrap" }, musicPlay(m), delMusic(m))))
        : h("p", { class: "mut" }, "Nenhuma música ainda. Sem músicas, o vídeo sai só com a narração.")),
    h("div", { class: "card" }, h("h3", {}, "Nova música"), field("Arquivo (mp3, wav, ogg, m4a)", file), field("Nome", name), field("Clima", mood), field("Licença", lic), field("Link de origem", src), btn));
}

const copyBtn = (getText, label = "Copiar") => h("button", { class: "ghost", type: "button", style: "flex:none;min-width:0;padding:4px 10px", onclick: async (ev) => {
  try { await navigator.clipboard.writeText(getText()); const b = ev.target; b.textContent = "Copiado ✓"; setTimeout(() => (b.textContent = label), 1500); } catch (e) { fail(e); }
} }, label);
function seoBox(seo) {
  if (!seo) return h("div", { class: "mut", style: "flex-basis:100%" }, "Textos do YouTube: sendo gerados (aparecem aqui em instantes). Se não aparecerem, rode a migration 0009 no Supabase.");
  const desc = h("textarea", { readonly: true, style: "min-height:180px" }); desc.value = seo.description || "";
  const tags = (seo.tags || []).join(", ");
  return h("details", { style: "flex-basis:100%" }, h("summary", { style: "cursor:pointer;color:var(--ac)" }, "Textos para o YouTube (títulos, descrição, tags)"),
    h("label", {}, "Títulos sugeridos"),
    ...(seo.titles || []).map((t) => h("div", { class: "row", style: "gap:8px;flex-wrap:nowrap;align-items:center;margin-bottom:4px" }, h("span", { style: "flex:1;min-width:0" }, t), copyBtn(() => t))),
    h("label", {}, "Descrição (já com capítulos)"), desc, copyBtn(() => desc.value, "Copiar descrição"),
    h("label", {}, "Tags (cole no campo de tags do YouTube)"), h("div", { class: "mut", style: "word-break:break-word" }, tags), copyBtn(() => tags, "Copiar tags"));
}

async function viewReady() {
  const rows = await load(sb.from("project_exports")
    .select("id,project_id,created_at,projects(title,seo),media_assets(storage_backend,bytes,origin_url)").order("created_at", { ascending: false }));
  const caps = await thumbsFor(rows.map((r) => r.project_id)).catch(() => new Map());
  const downCapa = (t) => h("button", { class: "ghost", onclick: async (ev) => {
    ev.target.disabled = true;
    try { const { data, error } = await sb.storage.from("media").createSignedUrl(t.key, 600, { download: "capa.jpg" }); if (error) throw error; location.href = data.signedUrl; } catch (e) { fail(e); }
    ev.target.disabled = false;
  } }, "Baixar capa");
  const newCapa = (r) => h("button", { class: "ghost", onclick: async (ev) => {
    ev.target.disabled = true;
    try {
      await load(sb.from("tasks").insert({ user_id: user.id, project_id: r.project_id, type: "generate_thumbnail", status: "QUEUED", priority: 5, payload: {}, idempotency_key: `thumb:${r.project_id}:${Date.now()}` }).select("id"));
      toast("Nova capa na fila. Em ~2 min, volte a esta aba (ou clique em Vídeos prontos) para ver.");
    } catch (e) { fail(e); ev.target.disabled = false; }
  } }, "Nova capa (IA)");
  const mb = (b) => (b ? `${(b / 1048576).toFixed(1)} MB` : "");
  const item = (r) => {
    const a = r.media_assets || {}, drive = a.storage_backend === "gdrive";
    const release = a.origin_url && a.origin_url.includes("/releases/download/");
    const when = new Date(r.created_at);
    const days = Math.max(0, 7 - Math.floor((Date.now() - when) / 86400000));
    const note = release ? "Download direto, sem prazo" : drive ? "Salvo no seu Google Drive" : days > 0 ? `Baixe pelo GitHub (login necessário) — some em ~${days} dia(s)` : "Expirado no GitHub (artifact de 7 dias)";
    const cap = caps.get(r.project_id);
    return h("div", { class: "item", style: "flex-wrap:wrap" }, capaImg(cap),
      h("div", { style: "flex:1;min-width:0" }, h("strong", {}, r.projects?.title || "Vídeo"), h("div", { class: "mut" }, `${when.toLocaleString("pt-BR")} · ${mb(a.bytes)} · ${note}`)),
      cap ? downCapa(cap) : null, newCapa(r),
      a.origin_url && (release || drive || days > 0) ? h("a", { class: "btn", href: a.origin_url, ...(release ? { download: "" } : { target: "_blank", rel: "noopener noreferrer" }) }, release ? "⬇ Baixar vídeo" : drive ? "Abrir / baixar" : "Baixar") : null, seoBox(r.projects?.seo));
  };
  app.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Vídeos prontos"),
    rows.length ? rows.map(item) : h("p", { class: "mut" }, "Nenhum vídeo pronto ainda. Quando um projeto terminar de renderizar, ele aparece aqui.")));
}

// ---------- navegacao ----------
const TABS = { home: ["Início", viewHome, "🏠"], projects: ["Projetos", viewProjects, "📁"], ready: ["Vídeos prontos", viewReady, "🎬"], music: ["Músicas", viewMusic, "🎵"], new: ["Novo projeto", viewNew, "➕"], channels: ["Canais", viewChannels, "📡"], voices: ["Vozes", viewVoices, "🎙"] };
function setTab(t) {
  tab = t;
  clearInterval(poll);
  $("nav").replaceChildren(...Object.entries(TABS).map(([k, [label, , icon]]) => h("button", { class: k === tab ? "on" : "", onclick: () => setTab(k) }, h("span", { class: "ic" }, icon), label)));
  TABS[t][1]().catch(fail);
}
document.addEventListener("visibilitychange", () => { if (!document.hidden && tab === "projects" && user) viewProjects().catch(() => {}); });
$("logout").addEventListener("click", () => sb.auth.signOut());

function onSession(session) {
  const prev = user;
  user = session?.user ?? null;
  if (!user) return authView();
  if (prev && prev.id === user.id) return; // renovacao de token ao voltar para a aba: nao redesenha
  $("top").hidden = false;
  $("who").textContent = user.email;
  setTab(tab);
}
sb.auth.onAuthStateChange((_e, session) => onSession(session));
sb.auth.getSession().then(({ data }) => onSession(data.session));

// ---------- aviso de nova versao (o navegador guarda o site em cache por ate 10 min) ----------
let loadedVersion = null;
async function checkVersion() {
  try {
    const r = await fetch(`version.json?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) return;
    const { v } = await r.json();
    if (loadedVersion === null) { loadedVersion = v; return; }
    if (v !== loadedVersion && !$("update")) {
      document.body.append(h("div", { id: "update", class: "update" }, "Nova versão disponível. ", h("button", { class: "pri", style: "margin:0 0 0 8px;padding:4px 12px", onclick: () => location.reload() }, "Atualizar")));
    }
  } catch {}
}
checkVersion();
setInterval(checkVersion, 60000);
