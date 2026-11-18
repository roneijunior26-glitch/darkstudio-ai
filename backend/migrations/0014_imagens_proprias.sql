-- 0014: o usuario pode enviar as proprias imagens das cenas (pasta <uid>/uploads/ do bucket media).
drop policy if exists media_uploads_insert on storage.objects;
create policy media_uploads_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'media' and (storage.foldername(name))[1] = auth.uid()::text and (storage.foldername(name))[2] = 'uploads');
drop policy if exists media_uploads_delete on storage.objects;
create policy media_uploads_delete on storage.objects for delete to authenticated
  using (bucket_id = 'media' and (storage.foldername(name))[1] = auth.uid()::text and (storage.foldername(name))[2] = 'uploads');
