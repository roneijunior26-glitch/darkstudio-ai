-- Teste manual das regras de acesso (RLS). Rode no SQL Editor do Supabase DEPOIS da 0001_init.sql.
--
-- 1) Authentication > Users > Add user: crie dois usuarios (e-mails quaisquer, senha qualquer).
-- 2) Copie o UUID de cada um e troque os dois valores abaixo (ua e ub).
-- 3) Rode. O script termina de proposito com um ERRO que mostra o relatorio.
--    Esse erro faz o Postgres desfazer tudo: nenhum dado de teste fica gravado.
--
-- ATENCAO: este script ainda nao foi executado em um Postgres real. Se falhar por erro de
-- sintaxe ou de configuracao do Supabase, o problema pode estar no script, nao nas regras.

do $$
declare
  ua uuid := '00000000-0000-0000-0000-00000000000a';  -- TROQUE: UUID do usuario A
  ub uuid := '00000000-0000-0000-0000-00000000000b';  -- TROQUE: UUID do usuario B
  n int;
  report text := '';
begin
  if not exists (select 1 from auth.users where id = ua)
     or not exists (select 1 from auth.users where id = ub) then
    raise exception 'UUIDs nao encontrados em auth.users. Troque ua e ub pelos UUIDs reais.';
  end if;

  -- Dados criados como administrador (ignora RLS).
  insert into channels (user_id, name) values (ua, 'canal A'), (ub, 'canal B');
  insert into youtube_accounts (user_id) values (ua);

  -- ===== Como usuario A =====
  perform set_config('request.jwt.claims',
    json_build_object('sub', ua::text, 'role', 'authenticated')::text, true);
  perform set_config('request.jwt.claim.sub', ua::text, true);

  -- T1: A so ve o proprio canal
  execute 'set local role authenticated';
  select count(*) into n from channels;
  execute 'reset role';
  report := report || format(E'%s T1 A ve so o proprio canal (viu %s)\n',
    case when n = 1 then 'OK   ' else 'FALHA' end, n);

  -- T2: A nao consegue criar canal em nome de B
  begin
    execute 'set local role authenticated';
    insert into channels (user_id, name) values (ub, 'invasao');
    execute 'reset role';
    report := report || E'FALHA T2 A conseguiu criar canal para B\n';
  exception when insufficient_privilege then
    report := report || E'OK    T2 A nao cria canal para B\n';
  end;

  -- T3: A nao consegue criar tarefa ja COMPLETED
  begin
    execute 'set local role authenticated';
    insert into tasks (user_id, type, status) values (ua, 'teste', 'COMPLETED');
    execute 'reset role';
    report := report || E'FALHA T3 A criou tarefa COMPLETED\n';
  exception when insufficient_privilege then
    report := report || E'OK    T3 A nao cria tarefa COMPLETED\n';
  end;

  -- T4: A consegue enfileirar tarefa QUEUED
  begin
    execute 'set local role authenticated';
    insert into tasks (user_id, type, status) values (ua, 'teste', 'QUEUED');
    execute 'reset role';
    report := report || E'OK    T4 A enfileira tarefa QUEUED\n';
  exception when others then
    report := report || format(E'FALHA T4 A nao conseguiu enfileirar (%s)\n', sqlerrm);
  end;

  -- T5: A nao consegue alterar o estado de uma tarefa
  begin
    execute 'set local role authenticated';
    update tasks set status = 'COMPLETED' where user_id = ua;
    get diagnostics n = row_count;
    execute 'reset role';
    report := report || format(E'%s T5 A nao altera estado de tarefa (%s linhas alteradas)\n',
      case when n = 0 then 'OK   ' else 'FALHA' end, n);
  exception when insufficient_privilege then
    report := report || E'OK    T5 A sem permissao de update em tasks\n';
  end;

  -- T6: A nao le o token do YouTube, mas le o resto da linha
  begin
    execute 'set local role authenticated';
    perform token_encrypted from youtube_accounts;
    execute 'reset role';
    report := report || E'FALHA T6 A leu token_encrypted\n';
  exception when insufficient_privilege then
    report := report || E'OK    T6 A nao le token_encrypted\n';
  end;

  execute 'set local role authenticated';
  select count(*) into n from youtube_accounts;
  execute 'reset role';
  report := report || format(E'%s T6b A le as colunas permitidas (viu %s linha)\n',
    case when n = 1 then 'OK   ' else 'FALHA' end, n);

  -- ===== Como usuario B =====
  perform set_config('request.jwt.claims',
    json_build_object('sub', ub::text, 'role', 'authenticated')::text, true);
  perform set_config('request.jwt.claim.sub', ub::text, true);

  -- T7: B nao ve tarefas nem canal de A
  execute 'set local role authenticated';
  select count(*) into n from tasks;
  execute 'reset role';
  report := report || format(E'%s T7 B nao ve tarefas de A (viu %s)\n',
    case when n = 0 then 'OK   ' else 'FALHA' end, n);

  execute 'set local role authenticated';
  select count(*) into n from channels where user_id = ua;
  execute 'reset role';
  report := report || format(E'%s T7b B nao ve canais de A (viu %s)\n',
    case when n = 0 then 'OK   ' else 'FALHA' end, n);

  -- ===== Sem login (anon) =====
  perform set_config('request.jwt.claims', '{"role":"anon"}', true);
  perform set_config('request.jwt.claim.sub', '', true);
  begin
    execute 'set local role anon';
    select count(*) into n from channels;
    execute 'reset role';
    report := report || format(E'%s T8 anonimo nao ve canais (viu %s)\n',
      case when n = 0 then 'OK   ' else 'FALHA' end, n);
  exception when insufficient_privilege then
    report := report || E'OK    T8 anonimo sem permissao nas tabelas\n';
  end;

  -- ===== Constraint de fornecedores (como administrador) =====
  begin
    insert into ai_providers (user_id, name, category, integration_type, tier, status, authorized)
    values (ua, 'video pago', 'video', 'api', 'PAID', 'enabled', false);
    report := report || E'FALHA T9 fornecedor PAID habilitado sem autorizacao foi aceito\n';
  exception when check_violation then
    report := report || E'OK    T9 PAID habilitado sem autorizacao e recusado\n';
  end;

  raise exception E'RESULTADO DO TESTE (este erro e esperado e desfaz tudo):\n%', report;
end $$;
