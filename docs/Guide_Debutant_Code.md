# Saros — Guide du code pour débutant

## 1. C'est quoi un endpoint ? C'est quoi une API ?

### Une API (Application Programming Interface)
Imagine un restaurant. Toi (le client) tu ne vas pas en cuisine préparer ton plat. Tu passes par le **serveur** (l'API) qui prend ta commande et te ramène le résultat.

Une API c'est pareil : c'est un **serveur** qui attend des demandes et retourne des réponses. Ton application Flutter (le client) envoie une demande, l'API la traite et retourne le résultat.

### Un endpoint (point d'entrée)
Un endpoint c'est **une adresse URL** qui correspond à une action précise du serveur.

Exemple concret :
```
POST https://saros-s5ut.onrender.com/anonymisation/detect
     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
     C'est l'endpoint. C'est "la porte d'entrée" pour
     déclencher la détection de données sensibles.
```

Notre module a **4 endpoints** (4 portes d'entrée) :
- `/login` → pour s'authentifier
- `/files/upload` → pour envoyer un fichier
- `/anonymisation/detect` → pour détecter les données sensibles
- `/anonymisation/execute` → pour anonymiser + envoyer au LLM
- `/anonymisation/audit` → pour consulter le journal

Chaque endpoint est une **fonction Python** dans le code, décorée avec `@app.get(...)` ou `@app.post(...)`.

---

## 2. Pourquoi plusieurs fichiers .py ?

C'est comme une entreprise. Tu ne mets pas tout le monde dans le même bureau. Chaque fichier a **un rôle précis** :

```
modules/anonymisation/
│
├── main.py              ← Le CHEF. Il reçoit les demandes et coordonne tout.
│                           C'est ici que sont les endpoints.
│
├── models.py            ← Le FORMULAIRE. Il définit la forme exacte des
│                           données échangées (qu'est-ce qu'on envoie,
│                           qu'est-ce qu'on reçoit).
│
├── config.py            ← Le CARNET D'ADRESSES. Toutes les configurations :
│                           clés API, adresses de serveurs, mots de passe.
│
├── auth.py              ← Le VIGILE. Il vérifie que tu as le droit d'entrer
│                           (login + vérification du token).
│
├── detector.py          ← Le DÉTECTIVE. Il cherche les données sensibles
│                           dans le texte (en appelant le LLM local).
│
├── pattern_detector.py  ← L'ASSISTANT DU DÉTECTIVE. Il cherche les formats
│                           connus (IBAN, email, n° TVA) avec des regex.
│
├── anonymizer.py        ← Le MASQUEUR. Il remplace les données sensibles
│                           par des placeholders ou du chiffrement.
│
├── llm_router.py        ← Le FACTEUR. Il envoie le message au bon LLM
│                           (Claude, GPT) et rapporte la réponse.
│
├── web_search.py        ← Le CHERCHEUR. Il va chercher des infos sur
│                           internet (via Tavily) pour enrichir la réponse.
│
├── storage.py           ← L'ARCHIVISTE. Il stocke et récupère les données
│                           dans MongoDB (fichiers, mappings, utilisateurs).
│
├── rgpd.py              ← Le LIVRE DE LOI. La liste des 27 catégories
│                           de données personnelles selon le RGPD.
│
└── file_handler.py      ← Le LECTEUR. Il sait ouvrir les fichiers
│                           (Excel, CSV, PDF) et en extraire le contenu.
```

**Pourquoi séparer ?** Parce que si tu dois modifier la façon dont on lit un PDF, tu touches UNIQUEMENT `file_handler.py`. Tu ne risques pas de casser le login ou l'anonymisation. Chaque fichier est **indépendant**.

---

## 3. Le code, fichier par fichier

### 3.1. config.py — Le carnet d'adresses (le plus simple)

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    file_storage_path: str = "/data/files"          # Où stocker les fichiers
    ollama_base_url: str = "http://localhost:11434"  # Adresse du LLM local
    ollama_model: str = "qwen2.5:14b-instruct"      # Quel modèle local utiliser
    encryption_key: str | None = None                # Clé de chiffrement (optionnelle)

    # MongoDB
    mongo_uri: str | None = None                     # Adresse de la base de données
    mongo_db_name: str = "saros"                     # Nom de la base

    # Auth
    jwt_secret: str = "change-me-in-production"      # Secret pour signer les tokens
    jwt_expiration_hours: int = 24                   # Durée de vie du token

    # Recherche web
    tavily_api_key: str | None = None                # Clé Tavily pour la recherche web

    # LLM externes
    anthropic_api_key: str | None = None             # Clé API Claude
    openai_api_key: str | None = None                # Clé API GPT

    model_config = {"env_prefix": "SAROS_ANON_"}     # Toutes les variables commencent par SAROS_ANON_

settings = Settings()
```

**Ce qu'il faut retenir :**
- `Settings` charge automatiquement les variables d'environnement
- `SAROS_ANON_MONGO_URI` dans Render → devient `settings.mongo_uri` dans le code
- Les valeurs après `=` sont les **valeurs par défaut** (utilisées si la variable n'existe pas)

---

### 3.2. models.py — Les formulaires

Ce fichier définit la **forme** des données. C'est comme un formulaire papier : on définit quels champs il contient.

```python
class OrchestrationRequest(BaseModel):
    requestId: str           # Identifiant unique de la requête
    userId: str              # Qui fait la demande
    conversationId: str      # À quelle conversation ça appartient
    message: str             # La question de l'utilisateur
    files: list[FileInfo] = []  # Les fichiers joints (optionnel)
    context: RequestContext  # Le contexte (application, langue)
```

Quand le front envoie un JSON, **FastAPI vérifie automatiquement** que le JSON correspond au formulaire. S'il manque un champ obligatoire → erreur 422.

Autre exemple :
```python
class AnonymizationStrategy(str, Enum):
    PLACEHOLDER = "placeholder"    # [NOM_1], [EMAIL_1]
    ENCRYPTION = "encryption"      # gAAAAABq... (chiffré)
```
C'est un **choix limité** : la stratégie est soit "placeholder" soit "encryption", rien d'autre.

---

### 3.3. auth.py — Le vigile

```python
def create_token(user_id: str) -> str:
```
Crée un **token JWT** — c'est comme un badge d'accès avec une date d'expiration.

```python
def verify_token(credentials) -> str:
```
Vérifie que le badge est valide. Si le token est expiré ou faux → erreur 401.

```python
def authenticate_user(user: str, password: str) -> str | None:
```
Vérifie le nom d'utilisateur et le mot de passe dans la base de données.

---

### 3.4. main.py — Le chef d'orchestre

C'est **LE** fichier central. C'est ici que les endpoints sont définis et que tout est coordonné.

#### Les imports (lignes 1-35)
```python
from .anonymizer import Anonymizer          # On importe le masqueur
from .auth import verify_token              # On importe le vigile
from .detector import detect_sensitive_entities  # On importe le détective
from .web_search import search_web          # On importe le chercheur web
# etc.
```
Le point `.` devant signifie "dans le même dossier".

#### Création de l'application (lignes 36-44)
```python
app = FastAPI(title="Saros - Module Anonymisation", version="0.5.0")
```
`app` c'est notre serveur. On lui ajoute le CORS (pour autoriser les appels depuis un navigateur).

#### Endpoint /login (pas de token requis)
```python
@app.get("/login")                          # ← "@app.get" = c'est un endpoint GET
async def login(user: str, password: str):  # ← les paramètres viennent de l'URL
    user_id = authenticate_user(user, password)  # Vérifie les credentials
    if not user_id:
        raise HTTPException(status_code=401, detail="Identifiants incorrects.")
    token = create_token(user_id)           # Crée le badge
    return {"token": token, "userId": user_id}  # Retourne le badge
```

#### Endpoint /anonymisation/detect (token requis)
```python
@app.post("/anonymisation/detect")          # ← "@app.post" = c'est un endpoint POST
async def detect(
    request: OrchestrationRequest,          # ← le JSON envoyé par le front
    current_user: str = Depends(verify_token),  # ← VÉRIFIE LE TOKEN AUTOMATIQUEMENT
):
```
`Depends(verify_token)` → avant d'exécuter la fonction, FastAPI appelle `verify_token`. Si le token est invalide, la fonction n'est jamais exécutée.

#### Endpoint /anonymisation/execute — le plus complexe
C'est ici que tout se passe. En interne, il appelle :
1. `anonymizer.py` → anonymise le texte
2. `web_search.py` → cherche sur le web (si activé)
3. `llm_router.py` → envoie au LLM externe (Claude/GPT)
4. `llm_router.py` → dé-anonymise la réponse

```python
# Simplifié :
async def _execute_text(request, pending):
    # 1. ANONYMISER
    anonymizer = Anonymizer(existing_mappings=existing)
    anonymized_message = anonymizer.anonymize_text(content, request.validatedEntities)
    # "Vincent Dupont" → "[NOM_1]"

    # 2. CHERCHER SUR LE WEB
    if request.webSearch:
        web_results = search_web(query=question, settings=settings)
        # Récupère des infos d'internet

    # 3. ENVOYER AU LLM
    llm_response = await _call_llm(content=llm_content, target_llm=request.targetLlm)
    # Claude reçoit "[NOM_1]" et répond avec "[NOM_1]"

    # 4. DÉ-ANONYMISER
    final_response = deanonymize(llm_response, anonymizer.get_mappings())
    # "[NOM_1]" → "Vincent Dupont"

    return ExecutionResponse(response=final_response)
```

---

### 3.5. detector.py — Le détective (détection hybride)

Ce fichier contient **deux méthodes de détection** qui travaillent ensemble :

```python
async def detect_sensitive_entities(user_message, settings):
    # COUCHE 1 : les regex (rapide, fiable, limité)
    pattern_results = detect_by_patterns(user_message)
    # Trouve : IBAN, emails, n° TVA, téléphones

    # COUCHE 2 : le LLM local (intelligent, plus lent)
    raw_response = await call_local_llm(prompt, settings)
    # Trouve : noms de personnes, d'entreprises, adresses

    # FUSION des deux
    # Pas de doublons, LLM prioritaire
    return merged
```

Il contient aussi les **prompts** — les instructions qu'on donne au LLM local pour qu'il sache quoi chercher. C'est du texte en français qui explique au LLM son rôle.

---

### 3.6. pattern_detector.py — L'assistant regex

```python
PATTERNS = [
    {
        "category": "IBAN",
        "pattern": re.compile(r"[A-Z]{2}\d{2}(?:[\s]?\d{4}){2,7}"),
        # ↑ C'est une expression régulière (regex).
        # Elle décrit le FORMAT d'un IBAN : 2 lettres, 2 chiffres, puis des groupes de 4 chiffres.
        # Si le texte contient quelque chose qui ressemble à ça → détecté.
    },
    # ... même chose pour email, téléphone, TVA, etc.
]
```

**Regex** = un motif de recherche. `[A-Z]{2}` veut dire "exactement 2 lettres majuscules".

---

### 3.7. anonymizer.py — Le masqueur

Deux stratégies :

```python
# PLACEHOLDER : remplace par un code lisible
"Vincent Dupont" → "[NOM_1]"
"Marie Martin"   → "[NOM_2]"
# Même personne = même placeholder (déduplication)

# ENCRYPTION : chiffre la valeur (réversible)
"BE36 0019 8525 8681" → "gAAAAABqgCbHY5R8t4Lmg..."
# On peut déchiffrer avec la clé stockée dans les mappings
```

Le fichier gère aussi la **continuité de conversation** :
```python
def __init__(self, existing_mappings=None):
    # Si on a déjà anonymisé "Vincent Dupont" → [NOM_1] dans un message précédent,
    # on réutilise le même placeholder dans le message suivant.
```

---

### 3.8. llm_router.py — Le facteur

```python
def resolve_provider(target_llm):
    # "claude-sonnet-4-6" → on utilise Anthropic
    # "gpt-4o"            → on utilise OpenAI

async def send_to_llm(content, target_llm, settings):
    # Envoie le message au bon fournisseur et retourne la réponse

def deanonymize(text, mappings):
    # Opération inverse : [NOM_1] → "Vincent Dupont"
    # + déchiffre les tokens Fernet (gAAAAABq... → valeur originale)
```

---

### 3.9. web_search.py — Le chercheur web

```python
def search_web(query, settings, include_domains=None):
    client = TavilyClient(api_key=settings.tavily_api_key)
    response = client.search(query=query)
    # Tavily cherche sur internet et retourne :
    # - Une synthèse
    # - Les sources (titre, URL, contenu)
    # On formate tout ça en texte qu'on injecte dans le prompt du LLM
```

---

### 3.10. storage.py — L'archiviste

Gère **tout** le stockage dans MongoDB :
- `save_pending_request()` / `get_pending_request()` → requêtes en attente
- `save_conversation_mappings()` / `get_conversation_mappings()` → mappings par conversation
- `save_file()` / `get_file()` → fichiers uploadés
- `save_user()` / `get_user()` → utilisateurs
- `save_anonymisation_audit()` / `get_anonymisation_audit()` → journal d'anonymisation

**Mode double :** si MongoDB n'est pas configuré, tout est stocké en mémoire (pour le dev local).

---

### 3.11. rgpd.py — Le livre de loi

```python
RGPD_CATEGORIES = [
    {"code": "NOM",     "label": "Nom de famille",    "article": "Article 4"},
    {"code": "PRENOM",  "label": "Prénom",             "article": "Article 4"},
    {"code": "EMAIL",   "label": "Adresse email",      "article": "Article 4"},
    # ... 27 catégories au total
]
```

Sert à construire le prompt du LLM local : "Voici les catégories RGPD, trouve celles qui correspondent aux données du texte."

---

### 3.12. file_handler.py — Le lecteur

```python
def load_file_from_storage(file_id, file_name):
    content = get_file(file_id, file_name)   # Récupère depuis MongoDB
    return pd.read_excel(io.BytesIO(content)) # Convertit en tableau pandas

def extract_text_from_pdf_storage(file_id, file_name):
    content = get_file(file_id, file_name)   # Récupère depuis MongoDB
    # Extrait le texte du PDF page par page via pdfplumber
```

---

## 4. Le flux complet — dans quel ordre les fichiers sont appelés

```
Utilisateur tape : "Quel est le salaire de Vincent Dupont ?"

1.  main.py          → detect()              Reçoit la demande
2.  auth.py          → verify_token()        Vérifie le badge
3.  detector.py      → detect_sensitive_entities()
4.  pattern_detector → detect_by_patterns()  Regex cherche IBAN, email...
5.  rgpd.py          → get_categories_for_prompt()  Prépare la liste RGPD
6.  detector.py      → call_local_llm()      Envoie au LLM local (Ollama)
7.  storage.py       → save_pending_request() Stocke l'état

    → RETOUR : liste des champs sensibles détectés
    → L'utilisateur valide dans l'interface

8.  main.py          → execute()             Reçoit la validation
9.  auth.py          → verify_token()        Vérifie le badge
10. storage.py       → get_pending_request() Récupère l'état
11. storage.py       → get_conversation_mappings()  Charge les anciens mappings
12. anonymizer.py    → anonymize_text()      "Vincent Dupont" → [NOM_1]
13. storage.py       → save_conversation_mappings()  Sauvegarde les mappings
14. storage.py       → save_anonymisation_audit()    Écrit dans le journal
15. web_search.py    → search_web()          Cherche sur internet (Tavily)
16. llm_router.py    → send_to_llm()         Envoie à Claude
17. llm_router.py    → deanonymize()         [NOM_1] → "Vincent Dupont"

    → RETOUR : "Le salaire de Vincent Dupont est de 1200 EUR."
```

---

## 5. Glossaire

| Terme | Signification |
|-------|---------------|
| **API** | Serveur qui attend des demandes et retourne des réponses |
| **Endpoint** | Une URL précise du serveur (= une action) |
| **GET** | Type de requête pour LIRE des données |
| **POST** | Type de requête pour ENVOYER des données |
| **JSON** | Format de données universel (clé: valeur) |
| **Token JWT** | Badge d'accès temporaire (expire après 24h) |
| **Bearer** | "Porteur" — le header HTTP qui contient le token |
| **Regex** | Motif de recherche textuel (ex: format d'un IBAN) |
| **Placeholder** | Texte de remplacement lisible ([NOM_1]) |
| **Fernet** | Algorithme de chiffrement réversible |
| **RGPD** | Règlement européen sur la protection des données |
| **Ollama** | Logiciel pour exécuter des LLM en local |
| **LLM** | Large Language Model (IA qui comprend le texte) |
| **MongoDB** | Base de données NoSQL (stocke des documents JSON) |
| **Tavily** | Service de recherche web optimisé pour les IA |
| **FastAPI** | Framework Python pour créer des API rapidement |
| **Pydantic** | Bibliothèque qui valide la forme des données |
| **CORS** | Autorisation pour qu'un navigateur appelle l'API |
| **Render** | Hébergeur cloud pour déployer le service |
