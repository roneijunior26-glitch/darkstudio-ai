-- DarkStudio AI: schema inicial (PostgreSQL / Supabase).
-- Convencoes: UUID, timestamptz em UTC, user_id em toda tabela de dominio, RLS ligada.
-- Segredos NUNCA ficam aqui: ai_providers guarda apenas o NOME do segredo (credential_ref).

create extension if not exists pgcrypto;

create or replace function set_updated_at() returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

-- Perfil do usuario (autenticacao fica em auth.users, do Supabase Auth).
create table profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now()
);

create table voice_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  engine text not null,                 -- ex.: piper, kokoro
  model_ref text not null,
  language text not null default 'pt-BR',
  category text,                        -- ex.: masculina_grave, narrador_documental
  speed numeric not null default 1.0,
  license text not null,                -- licenca da VOZ (obrigatorio, ver docs/providers.md)
  license_url text,
  created_at timestamptz not null default now()
);

create table niche_presets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  visual_style text,
  default_voice_id uuid references voice_profiles(id) on delete set null,
  music_prefs jsonb not null default '{}',
  thumbnail_style jsonb not null default '{}',
  seo_template jsonb not null default '{}',
  scene_rules jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table channels (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  description text,
  niche_preset_id uuid references niche_presets(id) on delete set null,
  language text not null default 'pt-BR',
  audience text,
  tone text,
  visual_identity jsonb not null default '{}',
  default_voice_id uuid references voice_profiles(id) on delete set null,
  thumbnail_style jsonb not null default '{}',
  seo_settings jsonb not null default '{}',
  music_prefs jsonb not null default '{}',
  publish_settings jsonb not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  channel_id uuid not null references channels(id),
  title text not null,
  input_mode text not null default 'script'
    check (input_mode in ('idea', 'story', 'script', 'research')),
  target_duration_s integer,
  video_format text not null default '1920x1080',
  fps integer not null default 30,
  visual_style text,
  anim_intensity text not null default 'medium',
  ai_video_ratio numeric not null default 0 check (ai_video_ratio between 0 and 1),
  status text not null default 'draft'
    check (status in ('draft','scripting','storyboard','producing','rendering',
                      'awaiting_approval','completed','failed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table scripts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  current_version_id uuid,
  approved_version_id uuid,
  created_at timestamptz not null default now()
);

create table script_versions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  script_id uuid not null references scripts(id) on delete cascade,
  version integer not null,
  content text not null,
  source text not null check (source in ('pasted', 'generated', 'edited')),
  approved boolean not null default false,
  created_at timestamptz not null default now(),
  unique (script_id, version)
);
alter table scripts
  add constraint scripts_current_fk foreign key (current_version_id) references script_versions(id),
  add constraint scripts_approved_fk foreign key (approved_version_id) references script_versions(id);

create table research_sources (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  url text not null,
  title text,
  published_at date,
  kind text not null default 'unknown' check (kind in ('fact','hypothesis','opinion','unknown')),
  note text,
  created_at timestamptz not null default now()
);

create table chapters (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  position integer not null,
  title text,
  text text,
  created_at timestamptz not null default now()
);

create table characters (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid references projects(id) on delete cascade,  -- null = biblioteca do usuario
  name text not null,
  description text,
  visual_traits text,
  clothing text,
  palette text,
  base_prompt text,
  created_at timestamptz not null default now()
);

create table locations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid references projects(id) on delete cascade,
  name text not null,
  era text,
  place text,
  architecture text,
  lighting text,
  palette text,
  traits text,
  created_at timestamptz not null default now()
);

create table media_assets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid references projects(id) on delete cascade,
  scene_id uuid,
  kind text not null check (kind in ('image','video','audio','subtitle','thumbnail','export')),
  storage_backend text not null check (storage_backend in ('supabase','gdrive','github_artifact')),
  storage_key text not null,
  bytes bigint,
  sha256 text,
  input_hash text,
  provider text,
  license text,
  origin_url text,
  is_intermediate boolean not null default false,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table scenes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  chapter_id uuid references chapters(id) on delete set null,
  position integer not null,
  narration_text text not null,
  est_duration_s numeric,
  duration_s numeric,                      -- real, medido no audio renderizado
  visual_description text,
  image_prompt text,
  video_prompt text,
  media_type text not null default 'still_motion' check (media_type in ('still_motion','ai_clip')),
  camera_move text,
  transition text,
  sfx text,
  music_cue text,
  character_ids uuid[] not null default '{}',
  location_id uuid references locations(id) on delete set null,
  input_hash text,
  image_asset_id uuid references media_assets(id) on delete set null,
  audio_asset_id uuid references media_assets(id) on delete set null,
  clip_asset_id uuid references media_assets(id) on delete set null,
  status text not null default 'draft'
    check (status in ('draft','approved','generating','ready','failed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);
alter table media_assets
  add constraint media_assets_scene_fk foreign key (scene_id) references scenes(id) on delete set null;

create table visual_references (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid references projects(id) on delete cascade,
  character_id uuid references characters(id) on delete cascade,
  location_id uuid references locations(id) on delete cascade,
  media_asset_id uuid not null references media_assets(id) on delete cascade,
  approved boolean not null default false,
  created_at timestamptz not null default now()
);

create table music_assets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  category text,
  media_asset_id uuid references media_assets(id) on delete set null,
  license text not null,                   -- obrigatorio: uso comercial precisa de autorizacao
  origin_url text not null,
  created_at timestamptz not null default now()
);

create table subtitles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  format text not null check (format in ('srt','vtt','json')),
  content text not null,
  style jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create table render_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  kind text not null check (kind in ('scene','project','cut')),
  status text not null default 'QUEUED',
  progress numeric not null default 0,
  log text,
  output_asset_id uuid references media_assets(id) on delete set null,
  created_at timestamptz not null default now(),
  finished_at timestamptz
);

create table project_exports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  asset_id uuid not null references media_assets(id) on delete cascade,
  kind text not null default 'mp4',
  created_at timestamptz not null default now()
);

create table thumbnails (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  asset_id uuid references media_assets(id) on delete set null,
  text_overlay text,
  approved boolean not null default false,
  created_at timestamptz not null default now()
);

create table video_cuts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  export_id uuid references project_exports(id) on delete cascade,
  segments jsonb not null,                 -- [{"in": 12.0, "out": 48.5}, ...] em segundos
  mode text not null default 'fast' check (mode in ('fast','precise')),
  status text not null default 'draft',
  output_asset_id uuid references media_assets(id) on delete set null,
  created_at timestamptz not null default now()
);

-- Fila de tarefas (reserva atomica com FOR UPDATE SKIP LOCKED; ver app/workers/queue.py).
create table tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid references projects(id) on delete cascade,
  type text not null,
  status text not null default 'QUEUED'
    check (status in ('PENDING','QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED',
                      'WAITING_PROVIDER','WAITING_APPROVAL')),
  payload jsonb not null default '{}',
  result jsonb,
  idempotency_key text,
  priority integer not null default 0,
  attempts integer not null default 0,
  max_attempts integer not null default 3,
  run_after timestamptz not null default now(),
  locked_by text,
  locked_at timestamptz,
  timeout_s integer not null default 1800,
  depends_on uuid[] not null default '{}',
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, idempotency_key)
);
create index tasks_claim_idx on tasks (status, run_after);
create index tasks_project_idx on tasks (user_id, project_id);

create table ai_providers (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  category text not null check (category in
    ('text','image','video','voice','transcription','translation','research')),
  integration_type text not null,
  endpoint text,
  credential_ref text,                     -- NOME do segredo (ex.: GEMINI_API_KEY), nunca o valor
  tier text not null default 'FREE' check (tier in ('FREE','OPTIONAL','PAID')),
  authorized boolean not null default false,
  status text not null default 'disabled',
  daily_limit numeric,                     -- null = desconhecido
  conservative_limit numeric,              -- usado quando daily_limit e null
  limit_unit text,
  priority integer not null default 100,
  last_checked_at timestamptz,
  created_at timestamptz not null default now(),
  -- PAID nunca pode estar habilitado sem autorizacao explicita.
  check (tier = 'FREE' or status = 'disabled' or authorized)
);

create table provider_usage (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  provider_id uuid not null references ai_providers(id) on delete cascade,
  task_id uuid references tasks(id) on delete set null,
  day date not null default (now() at time zone 'utc')::date,
  unit text not null,
  amount numeric not null,
  estimated boolean not null default true,
  created_at timestamptz not null default now()
);
create index provider_usage_day_idx on provider_usage (user_id, provider_id, day);

create table youtube_accounts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  channel_id uuid references channels(id) on delete set null,
  yt_channel_id text,
  token_encrypted bytea,                   -- criptografado; chave so no worker
  created_at timestamptz not null default now()
);

create table youtube_uploads (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references projects(id) on delete cascade,
  account_id uuid references youtube_accounts(id) on delete set null,
  video_id text,
  privacy text not null default 'private' check (privacy in ('private','unlisted','public')),
  status text not null default 'draft',
  created_at timestamptz not null default now()
);

create table audit_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  action text not null,
  entity text,
  entity_id uuid,
  detail jsonb not null default '{}',
  created_at timestamptz not null default now()
);

-- Indices de consulta frequente.
create index projects_user_idx on projects (user_id, channel_id) where deleted_at is null;
create index scenes_project_idx on scenes (project_id, position) where deleted_at is null;
create index media_assets_project_idx on media_assets (project_id);
create index chapters_project_idx on chapters (project_id, position);

-- updated_at automatico.
do $$
declare t text;
begin
  foreach t in array array['niche_presets','channels','projects','scenes','tasks'] loop
    execute format('create trigger %I_updated_at before update on %I
                    for each row execute function set_updated_at()', t, t);
  end loop;
end $$;

-- RLS: toda linha pertence a um usuario. O worker usa a service key (ignora RLS).
alter table profiles enable row level security;
create policy own_profile on profiles for all to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

do $$
declare t text;
begin
  foreach t in array array[
    'voice_profiles','niche_presets','channels','projects','scripts','script_versions',
    'research_sources','chapters','characters','locations','media_assets','scenes',
    'visual_references','music_assets','subtitles','render_jobs','project_exports',
    'thumbnails','video_cuts','ai_providers','youtube_accounts','youtube_uploads'
  ] loop
    execute format('alter table %I enable row level security', t);
    execute format('create policy own_rows on %I for all to authenticated
                    using (user_id = auth.uid()) with check (user_id = auth.uid())', t);
  end loop;
end $$;

-- Tabelas que o usuario so le (escrita apenas pelo worker/service key).
alter table provider_usage enable row level security;
create policy own_read on provider_usage for select to authenticated using (user_id = auth.uid());
alter table audit_logs enable row level security;
create policy own_read on audit_logs for select to authenticated using (user_id = auth.uid());

-- Tarefas: o usuario enfileira e consulta; nao altera estado (cancelar sera por funcao propria).
alter table tasks enable row level security;
create policy own_read on tasks for select to authenticated using (user_id = auth.uid());
create policy own_enqueue on tasks for insert to authenticated
  with check (user_id = auth.uid() and status in ('PENDING','QUEUED') and attempts = 0
              and locked_by is null and result is null);

-- Credenciais do YouTube nunca saem para o navegador.
revoke select on youtube_accounts from authenticated;
grant select (id, user_id, channel_id, yt_channel_id, created_at) on youtube_accounts to authenticated;
revoke insert, update on youtube_accounts from authenticated;
