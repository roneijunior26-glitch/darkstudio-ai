-- 0006: dispara o worker sozinho (GitHub Actions) quando ha tarefas na fila, sem custo.
-- O token do GitHub NUNCA fica neste arquivo: guarde-o no Vault (veja o passo 2 abaixo).

create extension if not exists pg_cron;
create extension if not exists pg_net;

create or replace function public.dispatch_worker() returns void
language plpgsql security definer set search_path = public, vault, net, extensions as $$
declare tok text;
begin
  -- nada para fazer
  if not exists (select 1 from tasks where status in ('QUEUED','WAITING_PROVIDER') and run_after <= now()) then return; end if;
  -- ja ha um worker trabalhando (ele pega as novas tarefas sozinho)
  if exists (select 1 from tasks where status = 'RUNNING' and locked_at > now() - interval '15 minutes') then return; end if;
  select decrypted_secret into tok from vault.decrypted_secrets where name = 'github_dispatch_token';
  if tok is null then return; end if;
  perform net.http_post(
    url := 'https://api.github.com/repos/roneijunior26-glitch/darkstudio-ai/actions/workflows/worker.yml/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'Accept', 'application/vnd.github+json',
                                  'X-GitHub-Api-Version', '2022-11-28', 'User-Agent', 'darkstudio-supabase'),
    body := jsonb_build_object('ref', 'main'));
end $$;

revoke all on function public.dispatch_worker() from public, anon, authenticated;

select cron.unschedule('dispatch-worker') where exists (select 1 from cron.job where jobname = 'dispatch-worker');
select cron.schedule('dispatch-worker', '*/2 * * * *', 'select public.dispatch_worker()');

-- PASSO 2 (rode UMA vez, trocando pelo seu token; nao envie o token a ninguem):
--   select vault.create_secret('COLE_O_TOKEN_AQUI', 'github_dispatch_token');
