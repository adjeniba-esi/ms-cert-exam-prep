// _providerMeta — routing par fournisseur IA (partagé par Exam-Prep.html et admin.html)
// _API_BASE est défini dans chaque fichier hôte avant toute interaction utilisateur.
function _providerMeta(model) {
  if (model === 'ollama')
    return {endpoint: _API_BASE+'/api/ollama', storageKey: null, label: 'Clé API', placeholder: 'sk-…'};
  if (model && model.startsWith('gpt-'))
    return {endpoint: _API_BASE+'/api/openai',  storageKey: '_ak_openai',  label: 'Clé API OpenAI',  placeholder: 'sk-…'};
  if (model && (model.startsWith('mistral-') || model.startsWith('open-mistral-')))
    return {endpoint: _API_BASE+'/api/mistral', storageKey: '_ak_mistral', label: 'Clé API Mistral', placeholder: 'sk-…'};
  return {endpoint: _API_BASE+'/api/translate', storageKey: '_ak', label: 'Clé API Anthropic', placeholder: 'sk-ant-…'};
}
