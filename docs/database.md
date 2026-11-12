# Banco de dados

Schema em `backend/migrations/0001_init.sql` (PostgreSQL / Supabase). **Estado: escrito, ainda não aplicado a um banco real.**

## Convenções

- IDs UUID, datas `timestamptz` (UTC), chaves estrangeiras, `deleted_at` onde há soft delete.
- Toda tabela de domínio tem `user_id`; RLS ligada com `user_id = auth.uid()`.
- O worker usa a service key do Supabase, que ignora RLS. Essa chave só existe em GitHub Secrets.
- Segredos não ficam no banco: `ai_providers.credential_ref` guarda apenas o nome do segredo.

## Tabelas

Perfil e conteúdo: `profiles`, `channels`, `niche_presets`, `projects`, `scripts`, `script_versions`, `research_sources`, `chapters`, `scenes`.

Visual e mídia: `characters`, `locations`, `visual_references`, `media_assets`, `voice_profiles`, `music_assets`, `subtitles`, `thumbnails`.

Produção: `tasks` (fila), `render_jobs`, `project_exports`, `video_cuts`.

Fornecedores e custo: `ai_providers`, `provider_usage`.

YouTube e auditoria: `youtube_accounts`, `youtube_uploads`, `audit_logs`.

## Regras de acesso

- Leitura e escrita pelo dono: a maioria das tabelas (política `own_rows`).
- Somente leitura para o usuário: `provider_usage`, `audit_logs`.
- `tasks`: o usuário consulta e enfileira (status inicial `PENDING`/`QUEUED`); não altera estado. Cancelamento virá por função própria.
- `youtube_accounts`: o navegador nunca lê `token_encrypted`.
- `ai_providers`: um fornecedor não-FREE não pode estar habilitado sem `authorized = true` (constraint).

## Pendências

- Aplicar a migration em um projeto Supabase e testar as políticas de RLS com dois usuários.
- Função de cancelamento de tarefas.
- Limite de tamanho por usuário para `tasks.payload`.
