-- 0013: vozes mais naturais e "inteligentes" (tom de divulgador cientifico / professor), alem das graves de documentario.
-- Rode no SQL Editor do Supabase. Adiciona as vozes para todos os usuarios; pode rodar de novo sem duplicar.

create or replace function seed_natural_voices(uid uuid) returns void
language sql security invoker as $$
  insert into voice_profiles (user_id, name, engine, model_ref, category, speed, license, license_url, style_prompt, fallback_engine)
  select uid, v.name, v.engine, v.model_ref, v.category, v.speed, v.license, v.license_url, v.style_prompt, v.fallback_engine from (values
    ('Gemini Sadaltager (explicativo)',  'gemini', 'gemini-3.1-flash-tts-preview:Sadaltager', 'masculina_natural',  1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, com voz natural, clara e inteligente, como um divulgador científico explicando com curiosidade e ritmo agradável', 'kokoro'),
    ('Gemini Rasalgethi (informativo)',  'gemini', 'gemini-3.1-flash-tts-preview:Rasalgethi', 'masculina_natural',  1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, em tom informativo e confiante, natural, como um bom professor', 'kokoro'),
    ('Gemini Achird (amigável)',         'gemini', 'gemini-3.1-flash-tts-preview:Achird',     'masculina_natural',  1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, de forma amigável, natural e envolvente, como numa conversa', 'kokoro'),
    ('Gemini Orus (firme)',              'gemini', 'gemini-3.1-flash-tts-preview:Orus',       'masculina_natural',  1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, com voz firme, clara e natural, sem exagero dramático', 'kokoro'),
    ('Gemini Gacrux (maduro)',           'gemini', 'gemini-3.1-flash-tts-preview:Gacrux',     'masculina_natural',  1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, com voz madura, tranquila e inteligente', 'kokoro'),
    ('Gemini Aoede (leve)',              'gemini', 'gemini-3.1-flash-tts-preview:Aoede',      'feminina_natural',   1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, com voz feminina leve, natural e clara, como uma boa divulgadora científica', 'kokoro'),
    ('Gemini Sulafat (calorosa)',        'gemini', 'gemini-3.1-flash-tts-preview:Sulafat',    'feminina_natural',   1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, com voz feminina calorosa, natural e inteligente', 'kokoro'),
    ('Gemini Erinome (clara)',           'gemini', 'gemini-3.1-flash-tts-preview:Erinome',    'feminina_natural',   1.0::numeric, 'Termos da Gemini API', 'https://ai.google.dev/gemini-api/terms', 'Narre em português do Brasil, com voz feminina clara, natural e precisa', 'kokoro'),
    ('Kokoro Dora (feminina)',           'kokoro', 'pf_dora',                                  'feminina_natural',   1.0::numeric, 'Apache-2.0', 'https://huggingface.co/hexgrad/Kokoro-82M', null, null)
  ) as v(name, engine, model_ref, category, speed, license, license_url, style_prompt, fallback_engine)
  where not exists (select 1 from voice_profiles p where p.user_id = uid and p.name = v.name);
$$;

select seed_natural_voices(id) from auth.users;
