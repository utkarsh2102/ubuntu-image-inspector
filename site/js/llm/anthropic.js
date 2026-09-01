/** Anthropic Messages API, called directly from the browser. */
export async function anthropicComplete({ baseUrl, model, apiKey }, { system, user, signal }) {
  const res = await fetch(`${baseUrl}/v1/messages`, {
    method: 'POST',
    signal,
    credentials: 'omit',
    headers: {
      'content-type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      // Required for browser-origin requests; without it the API rejects them.
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify({
      model,
      max_tokens: 2000,
      system,
      messages: [{ role: 'user', content: user }],
    }),
  });

  if (!res.ok) {
    throw new Error(`Anthropic API ${res.status}: ${(await res.text()).slice(0, 300)}`);
  }
  const data = await res.json();
  return (data.content || [])
    .filter((b) => b.type === 'text')
    .map((b) => b.text)
    .join('');
}
