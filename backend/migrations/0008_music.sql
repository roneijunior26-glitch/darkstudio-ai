-- 0008: musica de fundo. O usuario envia as faixas (so as que tem licenca) pela aba "Musicas".
alter table music_assets add column if not exists storage_key text;
alter table music_assets add column if not exists bytes bigint;
alter table projects add column if not exists music_enabled boolean not null default true;
alter table projects add column if not exists music_id uuid references music_assets(id) on delete set null;

-- o usuario envia/apaga somente na propria pasta <uid>/music/ do bucket media
drop policy if exists media_music_insert on storage.objects;
create policy media_music_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'media' and (storage.foldername(name))[1] = auth.uid()::text and (storage.foldername(name))[2] = 'music');
drop policy if exists media_music_delete on storage.objects;
create policy media_music_delete on storage.objects for delete to authenticated
  using (bucket_id = 'media' and (storage.foldername(name))[1] = auth.uid()::text and (storage.foldername(name))[2] = 'music');
