-- 0012: videos de ambiente. Permite ao usuario enviar a imagem em <uid>/ambient/ do bucket media.
drop policy if exists media_ambient_insert on storage.objects;
create policy media_ambient_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'media' and (storage.foldername(name))[1] = auth.uid()::text and (storage.foldername(name))[2] = 'ambient');
drop policy if exists media_ambient_delete on storage.objects;
create policy media_ambient_delete on storage.objects for delete to authenticated
  using (bucket_id = 'media' and (storage.foldername(name))[1] = auth.uid()::text and (storage.foldername(name))[2] = 'ambient');
