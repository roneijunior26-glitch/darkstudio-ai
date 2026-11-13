-- 0010: editor de cortes (nome, formato vertical e mensagem de erro por corte)
alter table video_cuts add column if not exists name text;
alter table video_cuts add column if not exists vertical boolean not null default false;
alter table video_cuts add column if not exists error text;
