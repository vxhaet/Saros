"""Test d'intégration avec Ollama en réel.

Crée un fichier Excel de test, appelle le LLM local pour la détection,
puis exécute l'anonymisation complète.

Usage : python -m pytest tests/test_ollama_integration.py -v -s
"""

import tempfile
from pathlib import Path

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient


def ollama_is_running() -> bool:
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=3.0)
        return r.status_code == 200
    except httpx.ConnectError:
        return False


pytestmark = pytest.mark.skipif(
    not ollama_is_running(), reason="Ollama non accessible sur localhost:11434"
)


@pytest.fixture()
def test_env(tmp_path):
    """Prépare un fichier Excel de test et configure le module."""
    # Créer le fichier de test
    file_dir = tmp_path / "file-001"
    file_dir.mkdir()
    file_path = file_dir / "clients.xlsx"

    df = pd.DataFrame(
        {
            "identifiant_client": ["CLI-001", "CLI-002", "CLI-003"],
            "nom": ["Dupont", "Martin", "Bernard"],
            "prenom": ["Jean", "Marie", "Pierre"],
            "email": [
                "jean.dupont@entreprise.fr",
                "marie.martin@gmail.com",
                "p.bernard@outlook.com",
            ],
            "telephone": ["06 01 02 03 04", "06 12 34 56 78", "06 98 76 54 32"],
            "adresse": [
                "12 rue de Paris, 75001 Paris",
                "34 avenue Victor Hugo, 69002 Lyon",
                "8 place de la République, 33000 Bordeaux",
            ],
            "date_naissance": ["1985-03-15", "1990-07-22", "1978-11-08"],
            "numero_secu": [
                "1 85 03 75 108 042 36",
                "2 90 07 69 382 011 47",
                "1 78 11 33 063 005 82",
            ],
            "iban": [
                "FR76 3000 6000 0112 3456 7890 189",
                "FR76 1234 5678 0012 3456 7890 123",
                "FR76 9876 5432 0098 7654 3210 456",
            ],
            "montant_achat": [150.00, 230.50, 89.99],
            "categorie_produit": ["Électronique", "Vêtements", "Alimentation"],
        }
    )
    df.to_excel(file_path, index=False)

    # Patcher les settings
    from modules.anonymisation.config import settings

    original_path = settings.file_storage_path
    settings.file_storage_path = str(tmp_path)

    from modules.anonymisation.main import app, _pending_requests

    _pending_requests.clear()

    yield TestClient(app), tmp_path

    settings.file_storage_path = original_path


DETECT_REQUEST = {
    "requestId": "integration-test-001",
    "userId": "user-test",
    "conversationId": "conv-test",
    "message": "Je voudrais anonymiser les données clients pour les envoyer à un assistant IA externe afin d'analyser les tendances d'achat.",
    "files": [
        {
            "fileId": "file-001",
            "name": "clients.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": 5000,
        }
    ],
    "context": {"application": "test_integration", "language": "fr"},
}


class TestOllamaIntegration:
    def test_detect_with_real_llm(self, test_env):
        """Le LLM local doit détecter les champs sensibles du fichier."""
        client, tmp_path = test_env

        response = client.post("/anonymisation/detect", json=DETECT_REQUEST)
        assert response.status_code == 200

        data = response.json()
        print("\n--- Résultat de la détection ---")
        print(f"Status : {data['status']}")
        print(f"Lignes : {data['totalRows']}")
        print(f"Colonnes : {data['columns']}")
        print(f"\nChamps sensibles détectés ({len(data['detectedFields'])}) :")
        for f in data["detectedFields"]:
            print(
                f"  - {f['field']:25s} | {f['category']:12s} | "
                f"{f['rgpdArticle']:12s} | {f['recommendedStrategy']:12s}"
            )
            print(f"    Justification : {f['justification']}")
            print(f"    Exemples : {f['samples']}")

        # Le LLM doit au minimum détecter nom, email, telephone
        detected_names = {f["field"] for f in data["detectedFields"]}
        assert "nom" in detected_names, "Le LLM n'a pas détecté la colonne 'nom'"
        assert "email" in detected_names, "Le LLM n'a pas détecté la colonne 'email'"

        # montant_achat et categorie_produit ne doivent PAS être détectés
        assert "montant_achat" not in detected_names
        assert "categorie_produit" not in detected_names

    def test_full_flow_with_real_llm(self, test_env):
        """Flux complet : détection LLM → validation → anonymisation."""
        client, tmp_path = test_env

        # 1. Détection
        detect_resp = client.post("/anonymisation/detect", json=DETECT_REQUEST)
        assert detect_resp.status_code == 200
        detected = detect_resp.json()

        # 2. Construire la validation à partir de la détection du LLM
        validated_fields = [
            {
                "field": f["field"],
                "category": f["category"],
                "strategy": f["recommendedStrategy"],
            }
            for f in detected["detectedFields"]
        ]

        # 3. Exécution
        exec_resp = client.post(
            "/anonymisation/execute",
            json={
                "requestId": DETECT_REQUEST["requestId"],
                "userId": "user-test",
                "validatedFields": validated_fields,
            },
        )
        assert exec_resp.status_code == 200
        result = exec_resp.json()

        print("\n--- Résultat de l'anonymisation ---")
        print(f"Fichier : {result['anonymizedFilePath']}")
        print(f"Mappings : {result['mappingFilePath']}")
        print(f"Stats : {result['stats']}")

        # Vérifier le fichier anonymisé
        anon_df = pd.read_excel(result["anonymizedFilePath"])
        print(f"\n--- Aperçu du fichier anonymisé ---")
        print(anon_df.to_string(index=False))

        # Les noms ne doivent plus apparaître en clair
        original_names = {"Dupont", "Martin", "Bernard"}
        anonymized_names = set(anon_df["nom"].tolist())
        assert anonymized_names.isdisjoint(original_names), (
            f"Des noms en clair subsistent : {anonymized_names & original_names}"
        )

        # Les montants doivent être intacts
        assert anon_df["montant_achat"].tolist() == [150.00, 230.50, 89.99]
