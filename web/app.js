import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";
import { SUPABASE_URL, SUPABASE_KEY } from "./config.js";

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);
const $ = (id) => document.getElementById(id);
const app = $("app");
let user = null;
let tab = "projects";

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
async function viewProjects() {
  const rows = await load(sb.from("projects").select("id,title,status,created_at,channels(name)").is("deleted_at", null).order("created_at", { ascending: false }));
  app.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Projetos"),
    rows.length ? rows.map((p) => h("div", { class: "item" },
      h("div", {}, h("strong", {}, p.title), h("div", { class: "mut" }, `${p.channels?.name ?? "—"} · ${new Date(p.created_at).toLocaleString("pt-BR")}`)),
      h("span", { class: "tag" }, p.status))) : h("p", { class: "mut" }, "Nenhum projeto ainda. Crie o primeiro em “Novo projeto”.")));
}

async function viewNew() {
  const [chs, nis, vs] = await Promise.all([channels(), niches(), voices()]);
  if (!chs.length) { app.replaceChildren(h("div", { class: "card" }, h("p", {}, "Cadastre um canal primeiro, na aba Canais."))); return; }
  const title = h("input", { placeholder: "Título do vídeo" });
  const ch = h("select", {}, options(chs, "Escolha o canal").slice(1));
  const voice = h("select", {}, options(vs, "Voz padrão do canal"));
  const script = h("textarea", { placeholder: "Cole aqui o roteiro / narração completa…" });
  const btn = h("button", { class: "pri" }, "Criar projeto e iniciar");
  btn.addEventListener("click", async () => {
    try {
      if (!title.value.trim() || !script.value.trim()) throw new Error("Preencha título e roteiro.");
      btn.disabled = true;
      const c = chs.find((x) => x.id === ch.value);
      const niche = nis.find((n) => n.id === c.niche_preset_id);
      const voiceId = voice.value || c.default_voice_id || niche?.default_voice_id || null;
      const [proj] = await load(sb.from("projects").insert({ user_id: user.id, channel_id: c.id, title: title.value.trim(), input_mode: "script", visual_style: niche?.visual_style ?? null, voice_id: voiceId, status: "scripting" }).select("id"));
      const [sc] = await load(sb.from("scripts").insert({ user_id: user.id, project_id: proj.id }).select("id"));
      const [ver] = await load(sb.from("script_versions").insert({ user_id: user.id, script_id: sc.id, version: 1, content: script.value, source: "pasted" }).select("id"));
      await load(sb.from("scripts").update({ current_version_id: ver.id }).eq("id", sc.id).select("id"));
      await load(sb.from("tasks").insert({ user_id: user.id, project_id: proj.id, type: "split_scenes", status: "QUEUED", payload: { script_version_id: ver.id, voice_id: voiceId }, idempotency_key: `split:${ver.id}` }).select("id"));
      toast("Projeto criado. A divisão em cenas entrou na fila.");
      setTab("projects");
    } catch (e) { fail(e); btn.disabled = false; }
  });
  app.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Novo projeto"),
    field("Título", title),
    h("div", { class: "row" }, field("Canal", ch), field("Voz (opcional)", voice)),
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

async function viewVoices() {
  const rows = await load(sb.from("voice_profiles").select("name,engine,category,license").order("name"));
  app.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Vozes"),
    rows.length ? rows.map((v) => h("div", { class: "item" }, h("div", {}, h("strong", {}, v.name), h("div", { class: "mut" }, `${v.engine} · ${v.category ?? ""} · ${v.license}`)))) : h("p", { class: "mut" }, "Nenhuma voz. Rode a migration 0002 no Supabase.")));
}

// ---------- navegacao ----------
const TABS = { projects: ["Projetos", viewProjects], new: ["Novo projeto", viewNew], channels: ["Canais", viewChannels], voices: ["Vozes", viewVoices] };
function setTab(t) {
  tab = t;
  $("nav").replaceChildren(...Object.entries(TABS).map(([k, [label]]) => h("button", { class: k === tab ? "on" : "", onclick: () => setTab(k) }, label)));
  TABS[t][1]().catch(fail);
}
$("logout").addEventListener("click", () => sb.auth.signOut());

function onSession(session) {
  user = session?.user ?? null;
  if (!user) return authView();
  $("top").hidden = false;
  $("who").textContent = user.email;
  setTab(tab);
}
sb.auth.onAuthStateChange((_e, session) => onSession(session));
sb.auth.getSession().then(({ data }) => onSession(data.session));
