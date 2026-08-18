"""Recherche web via Tavily.

Enrichit les requêtes avec des informations du web avant envoi au LLM.
Supporte la recherche générale et la recherche ciblée sur des domaines spécifiques.
"""

from tavily import TavilyClient

from ..anonymisation.config import Settings


def search_web(
    query: str,
    settings: Settings,
    max_results: int = 5,
    include_domains: list[str] | None = None,
) -> str | None:
    """Effectue une recherche web et retourne les résultats formatés.

    Args:
        query: La question de l'utilisateur.
        settings: Configuration (clé API Tavily).
        max_results: Nombre de résultats à retourner.
        include_domains: Si fourni, restreint la recherche à ces domaines
                         (ex: ["eur-lex.europa.eu", "ejustice.just.fgov.be"]).

    Returns:
        Texte formaté avec les résultats, ou None si Tavily non configuré.
    """
    if not settings.tavily_api_key:
        return None

    client = TavilyClient(api_key=settings.tavily_api_key)

    search_params = {
        "query": query,
        "max_results": max_results,
        "include_answer": True,
    }
    if include_domains:
        search_params["include_domains"] = include_domains

    response = client.search(**search_params)

    # Formater les résultats pour le LLM
    parts = []

    # Réponse synthétique de Tavily
    if response.get("answer"):
        parts.append(f"Synthèse web : {response['answer']}")

    # Sources détaillées
    results = response.get("results", [])
    if results:
        parts.append("\nSources web :")
        for i, r in enumerate(results, 1):
            parts.append(f"\n[{i}] {r['title']}")
            parts.append(f"    URL : {r['url']}")
            if r.get("content"):
                # Limiter le contenu pour ne pas surcharger le prompt
                content = r["content"][:500]
                parts.append(f"    Contenu : {content}")

    return "\n".join(parts) if parts else None
