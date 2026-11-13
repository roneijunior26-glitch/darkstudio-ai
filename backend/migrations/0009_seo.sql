-- 0009: textos de SEO do YouTube gerados por video (titulos, descricao com capitulos, tags)
alter table projects add column if not exists seo jsonb;
