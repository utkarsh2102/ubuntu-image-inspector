/**
 * Provider-agnostic LLM access.
 *
 * Adding a provider is one entry here plus (if it is not OpenAI-compatible) one
 * adapter file. Nothing outside js/llm/ knows a provider exists, and the
 * deterministic analysis has no code path into this module at all -- the whole
 * tree is dynamically imported only when the panel is opened.
 *
 * Browser-direct calls are verified to work: api.anthropic.com and openrouter.ai
 * both answer CORS preflight with `access-control-allow-origin: *`.
 */
import { anthropicComplete } from './anthropic.js';
import { openaiCompatComplete } from './openai-compat.js';

export const PROVIDERS = {
  anthropic: {
    id: 'anthropic',
    label: 'Claude (Anthropic API)',
    defaultBaseUrl: 'https://api.anthropic.com',
    defaultModel: 'claude-opus-5',
    models: ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5'],
    keyHint: 'sk-ant-…',
    complete: anthropicComplete,
  },
  openrouter: {
    id: 'openrouter',
    label: 'OpenRouter',
    defaultBaseUrl: 'https://openrouter.ai/api/v1',
    defaultModel: 'anthropic/claude-opus-5',
    models: [
      'anthropic/claude-opus-5',
      'openai/gpt-5',
      'deepseek/deepseek-chat',
      'google/gemini-2.5-pro',
    ],
    keyHint: 'sk-or-…',
    complete: openaiCompatComplete,
  },
  deepseek: {
    id: 'deepseek',
    label: 'DeepSeek',
    defaultBaseUrl: 'https://api.deepseek.com/v1',
    defaultModel: 'deepseek-chat',
    models: ['deepseek-chat', 'deepseek-reasoner'],
    keyHint: 'sk-…',
    complete: openaiCompatComplete,
  },
  custom: {
    id: 'custom',
    label: 'Other OpenAI-compatible endpoint',
    defaultBaseUrl: '',
    defaultModel: '',
    models: [],
    keyHint: 'optional',
    // A custom host is not in the page CSP connect-src allowlist; using one
    // means editing index.html in a fork. Documented, never silently widened.
    complete: openaiCompatComplete,
    note: 'Requires adding the host to the Content-Security-Policy in index.html.',
  },
};

export async function complete(config, { system, user, signal }) {
  const provider = PROVIDERS[config.provider];
  if (!provider) throw new Error(`Unknown provider: ${config.provider}`);
  return provider.complete(
    {
      baseUrl: (config.baseUrl || provider.defaultBaseUrl).replace(/\/+$/, ''),
      model: config.model || provider.defaultModel,
      apiKey: config.apiKey,
    },
    { system, user, signal }
  );
}
