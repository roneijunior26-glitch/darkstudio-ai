-- 0004: funcoes usadas pelo worker (via REST com a chave service_role; ninguem mais pode chama-las)

create or replace function claim_task(p_worker text) returns setof tasks
language sql security definer set search_path = public as $$
  update tasks
     set status = 'RUNNING', locked_by = p_worker, locked_at = now(),
         attempts = attempts + 1, updated_at = now()
   where id = (
     select t.id from tasks t
      where t.status in ('QUEUED', 'WAITING_PROVIDER')
        and t.run_after <= now()
        and not exists (select 1 from tasks d where d.id = any(t.depends_on) and d.status <> 'COMPLETED')
      order by t.priority desc, t.run_after, t.created_at
      for update skip locked
      limit 1)
  returning *;
$$;

create or replace function reclaim_stuck_tasks() returns integer
language sql security definer set search_path = public as $$
  with r as (
    update tasks
       set status = case when attempts >= max_attempts then 'FAILED' else 'QUEUED' end,
           locked_by = null, locked_at = null,
           last_error = 'timeout: tarefa travada devolvida a fila', updated_at = now()
     where status = 'RUNNING' and locked_at < now() - make_interval(secs => timeout_s)
    returning 1)
  select count(*)::int from r;
$$;

revoke all on function claim_task(text), reclaim_stuck_tasks() from public, anon, authenticated;
grant execute on function claim_task(text), reclaim_stuck_tasks() to service_role;
