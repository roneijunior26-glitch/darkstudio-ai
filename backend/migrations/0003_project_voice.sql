-- 0003: voz escolhida por projeto (a voz padrao vem do canal, mas pode ser trocada por video)
alter table projects add column if not exists voice_id uuid references voice_profiles(id) on delete set null;
