-- 0007: refazer tarefas que falharam

-- (a) UMA VEZ: devolve a fila as tarefas de imagem/narracao que falharam pelo bug da consulta de cota
update tasks set status = 'QUEUED', attempts = 0, run_after = now(), last_error = null,
                 locked_by = null, locked_at = null, updated_at = now()
 where status = 'FAILED' and type in ('generate_image', 'generate_audio');

-- (b) funcao usada pelo botao "Tentar de novo" do site (so mexe nas tarefas do proprio usuario)
create or replace function public.retry_failed_tasks(p_project uuid) returns integer
language sql security definer set search_path = public as $$
  with r as (
    update tasks set status = 'QUEUED', attempts = 0, run_after = now(), last_error = null,
                     locked_by = null, locked_at = null, updated_at = now()
     where project_id = p_project and user_id = auth.uid() and status = 'FAILED'
    returning 1)
  select count(*)::int from r;
$$;
revoke all on function public.retry_failed_tasks(uuid) from public, anon;
grant execute on function public.retry_failed_tasks(uuid) to authenticated;
