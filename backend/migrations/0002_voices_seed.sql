-- 0002: biblioteca de vozes (escolhidas pelo usuario na Fase 0, 13/11/2026)
-- Rode no SQL Editor do Supabase. Depois, para cada usuario: select seed_default_voices('<uuid>');

alter table voice_profiles add column if not exists style_prompt text;   -- so Gemini: tom da narracao
alter table voice_profiles add column if not exists fallback_engine text; -- motor reserva se faltar cota

create or replace function seed_default_voices(uid uuid) returns void
language sql security invoker as $$
  insert into voice_profiles (user_id, name, engine, model_ref, category, speed, license, license_url, style_prompt, fallback_engine)
  select uid, v.* from (values
    ('Gemini Kore (documentário)',    'gemini', 'gemini-3.1-flash-tts-preview:Kore',   'narrador_documental', 1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, em tom grave e misterioso, de documentário', 'kokoro'),
    ('Gemini Charon (documentário)',  'gemini', 'gemini-3.1-flash-tts-preview:Charon', 'masculina_grave',     1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, em tom grave e misterioso, de documentário', 'kokoro'),
    ('Gemini Charon (2.5)',           'gemini', 'gemini-2.5-flash-preview-tts:Charon', 'masculina_grave',     1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, em tom grave e misterioso, de documentário', 'kokoro'),
    ('Kokoro Santa',                  'kokoro', 'pm_santa',                            'masculina_grave',     0.95::numeric, 'Apache-2.0', 'https://huggingface.co/hexgrad/Kokoro-82M', null, null),
    ('Kokoro Alex',                   'kokoro', 'pm_alex',                             'masculina',           0.95::numeric, 'Apache-2.0', 'https://huggingface.co/hexgrad/Kokoro-82M', null, null),
    ('Edge Thalita (multilíngue)',    'edge',   'pt-BR-ThalitaMultilingualNeural',     'feminina',            1.0::numeric, 'API nao oficial da Microsoft; sem garantia de uso comercial', null, null, 'kokoro')
  ) as v(name, engine, model_ref, category, speed, license, license_url, style_prompt, fallback_engine)
  where not exists (select 1 from voice_profiles p where p.user_id = uid and p.name = v.name);
$$;
