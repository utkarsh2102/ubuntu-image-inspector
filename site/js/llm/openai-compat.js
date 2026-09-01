/** OpenAI-compatible chat completions: OpenRouter, DeepSeek, local servers. */
export async function openaiCompatComplete(
  { baseUrl, model, apiKey },
  { system, user, signal }
) {
  const headers = { 'content-type': 'application/json' };
  if (apiKey) headers.authorization = `Bearer ${apiKey}`;
  if (/openrouter\.ai/.test(baseUrl)) {
    headers['X-Title'] = 'Ubuntu Image Inspector';
  }

  const res = await fetch(`${baseUrl}/chat/completions`, {
    method: 'POST',
    signal,
    credentials: 'omit',
    headers,
    body: JSON.stringify({
      model,
      max_tokens: 2000,
      messages: [
        { role: 'system', content: system },
        { role: 'user', content: user },
      ],
    }),
  });

  if (!res.ok) {
    throw new Error(`Provider ${res.status}: ${(await res.text()).slice(0, 300)}`);
  }
  const data = await res.json();
  return data.choices?.[0]?.message?.content || '';
}
