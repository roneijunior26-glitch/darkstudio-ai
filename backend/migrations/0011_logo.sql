-- 0011: logo do canal (marca d'agua nos videos). Arquivo em <uid>/logos/ do bucket media.
alter table channels add column if not exists logo_key text;

drop policy if exists media_logo_insert on storage.objects;
create policy media_logo_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'media' and (storage.foldername(name))[1] = auth.uid()::text and (storage.foldername(name))[2] = 'logos');
drop policy if exists media_logo_delete on storage.objects;
create policy media_logo_delete on storage.objects for delete to authenticated
  using (bucket_id = 'media' and (storage.foldername(name))[1] = auth.uid()::text and (storage.foldername(name))[2] = 'logos');
