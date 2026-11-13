-- 0005: bucket privado "media" (imagens/audios intermediarios) e leitura so da propria pasta
insert into storage.buckets (id, name, public) values ('media', 'media', false) on conflict (id) do nothing;

drop policy if exists media_read_own on storage.objects;
create policy media_read_own on storage.objects for select to authenticated
  using (bucket_id = 'media' and (storage.foldername(name))[1] = auth.uid()::text);
-- escrita: somente o worker (service_role ignora RLS); usuarios nao escrevem direto.
