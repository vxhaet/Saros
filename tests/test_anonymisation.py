"""Tests du module anonymisation.

Lance le flux complet : détection (LLM mocké) → exécution → vérification.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from modules.anonymisation.anonymizer import Anonymizer
from modules.anonymisation.file_handler import extract_samples, load_file
from modules.anonymisation.llm_router import deanonymize, resolve_provider
from modules.anonymisation.models import AnonymizationStrategy, FieldValidation


# ── Données de test ──────────────────────────────────────────────────


def create_test_excel(directory: str) -> str:
    """Crée un fichier Excel avec des données fictives."""
    file_dir = Path(directory) / "file-001"
    file_dir.mkdir(parents=True, exist_ok=True)
    file_path = file_dir / "clients.xlsx"

    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "nom": ["Dupont", "Martin", "Bernard", "Petit", "Durand"],
            "prenom": ["Jean", "Marie", "Pierre", "Sophie", "Luc"],
            "email": [
                "jean.dupont@mail.com",
                "marie.martin@mail.com",
                "p.bernard@mail.com",
                "sophie.petit@mail.com",
                "luc.durand@mail.com",
            ],
            "telephone": [
                "0601020304",
                "0612345678",
                "0698765432",
                "0611223344",
                "0655667788",
            ],
            "adresse": [
                "12 rue de Paris, 75001 Paris",
                "34 avenue Victor Hugo, 69002 Lyon",
                "8 place de la République, 33000 Bordeaux",
                "56 boulevard Haussmann, 75008 Paris",
                "2 rue du Port, 44000 Nantes",
            ],
            "date_naissance": [
                "1985-03-15",
                "1990-07-22",
                "1978-11-08",
                "1995-01-30",
                "1982-06-12",
            ],
            "montant_achat": [150.00, 230.50, 89.99, 445.00, 67.30],
        }
    )
    df.to_excel(file_path, index=False)
    return directory


# Réponse simulée du LLM local
MOCK_LLM_RESPONSE = json.dumps(
    {
        "detectedFields": [
            {
                "field": "nom",
                "category": "NOM",
                "rgpdArticle": "Article 4",
                "recommendedStrategy": "placeholder",
                "justification": "Donnée d'identité envoyée vers un LLM externe.",
            },
            {
                "field": "prenom",
                "category": "NOM",
                "rgpdArticle": "Article 4",
                "recommendedStrategy": "placeholder",
                "justification": "Prénom, donnée d'identité directe.",
            },
            {
                "field": "email",
                "category": "EMAIL",
                "rgpdArticle": "Article 4",
                "recommendedStrategy": "encryption",
                "justification": "Email servant d'identifiant unique, chiffrement pour ré-identification.",
            },
            {
                "field": "telephone",
                "category": "TELEPHONE",
                "rgpdArticle": "Article 4",
                "recommendedStrategy": "placeholder",
                "justification": "Numéro de téléphone, placeholder suffisant pour le contexte.",
            },
            {
                "field": "adresse",
                "category": "ADRESSE",
                "rgpdArticle": "Article 4",
                "recommendedStrategy": "placeholder",
                "justification": "Adresse postale complète, donnée personnelle directe.",
            },
            {
                "field": "date_naissance",
                "category": "DATE_NAISS",
                "rgpdArticle": "Article 4",
                "recommendedStrategy": "encryption",
                "justification": "Date de naissance, chiffrement pour permettre des calculs ultérieurs.",
            },
        ]
    }
)


# ── Tests unitaires ──────────────────────────────────────────────────


class TestFileHandler:
    def test_load_excel(self, tmp_path):
        create_test_excel(str(tmp_path))
        file_path = str(tmp_path / "file-001" / "clients.xlsx")
        df = load_file(file_path)
        assert len(df) == 5
        assert "nom" in df.columns
        assert "email" in df.columns

    def test_extract_samples(self, tmp_path):
        create_test_excel(str(tmp_path))
        file_path = str(tmp_path / "file-001" / "clients.xlsx")
        df = load_file(file_path)
        samples = extract_samples(df, n=2)
        assert len(samples["nom"]) == 2
        assert samples["nom"][0] == "Dupont"

    def test_unsupported_format(self, tmp_path):
        bad_file = tmp_path / "data.txt"
        bad_file.write_text("hello")
        with pytest.raises(ValueError, match="Format non supporté"):
            load_file(str(bad_file))


class TestAnonymizer:
    def test_placeholder_strategy(self):
        df = pd.DataFrame(
            {
                "nom": ["Dupont", "Martin", "Dupont"],
                "ville": ["Paris", "Lyon", "Paris"],
            }
        )
        fields = [
            FieldValidation(
                field="nom", category="NOM", strategy=AnonymizationStrategy.PLACEHOLDER
            )
        ]
        anonymizer = Anonymizer()
        result = anonymizer.anonymize(df, fields)

        # Les noms sont remplacés par des placeholders
        assert result["nom"].iloc[0] == "[NOM_1]"
        assert result["nom"].iloc[1] == "[NOM_2]"
        # Dupont apparaît 2 fois → même placeholder
        assert result["nom"].iloc[2] == "[NOM_1]"
        # Ville non anonymisée
        assert result["ville"].iloc[0] == "Paris"

    def test_encryption_strategy(self):
        df = pd.DataFrame({"email": ["test@mail.com", "other@mail.com"]})
        fields = [
            FieldValidation(
                field="email",
                category="EMAIL",
                strategy=AnonymizationStrategy.ENCRYPTION,
            )
        ]
        anonymizer = Anonymizer()
        result = anonymizer.anonymize(df, fields)

        # Les emails sont chiffrés (pas les originaux)
        assert result["email"].iloc[0] != "test@mail.com"
        assert result["email"].iloc[1] != "other@mail.com"

        # Le chiffrement est réversible
        from cryptography.fernet import Fernet

        fernet = Fernet(anonymizer.key)
        decrypted = fernet.decrypt(result["email"].iloc[0].encode()).decode()
        assert decrypted == "test@mail.com"

    def test_mappings_saved(self, tmp_path):
        df = pd.DataFrame({"nom": ["Dupont", "Martin"]})
        fields = [
            FieldValidation(
                field="nom", category="NOM", strategy=AnonymizationStrategy.PLACEHOLDER
            )
        ]
        anonymizer = Anonymizer()
        anonymizer.anonymize(df, fields)

        output_path = str(tmp_path / "output.xlsx")
        mappings_path = anonymizer.save_mappings(output_path)

        with open(mappings_path) as f:
            mappings = json.load(f)

        assert "[NOM_1]" in mappings["placeholder_mappings"]["NOM"]
        assert mappings["placeholder_mappings"]["NOM"]["[NOM_1]"] == "Dupont"
        assert "encryption_key" in mappings


# ── Test d'intégration API ───────────────────────────────────────────


class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Prépare l'environnement de test avec un fichier Excel et le mock LLM."""
        self.storage_path = str(tmp_path)
        create_test_excel(self.storage_path)

        # Patch les settings et le LLM
        with (
            patch(
                "modules.anonymisation.main.settings"
            ) as mock_settings,
            patch(
                "modules.anonymisation.detector.call_local_llm",
                new_callable=AsyncMock,
                return_value=MOCK_LLM_RESPONSE,
            ),
            patch(
                "modules.anonymisation.main._call_llm",
                new_callable=AsyncMock,
                return_value="Réponse du LLM avec [NOM_1] anonymisé.",
            ),
        ):
            mock_settings.file_storage_path = self.storage_path
            mock_settings.encryption_key = None

            from modules.anonymisation.main import app
            from modules.anonymisation.storage import (
                _memory_pending,
                _memory_conversations,
            )

            _memory_pending.clear()
            _memory_conversations.clear()
            self.client = TestClient(app)
            yield

    def test_detect_endpoint(self):
        response = self.client.post(
            "/anonymisation/detect",
            json={
                "requestId": "test-001",
                "userId": "user-1",
                "conversationId": "conv-1",
                "message": "Anonymiser les données clients",
                "files": [
                    {
                        "fileId": "file-001",
                        "name": "clients.xlsx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "size": 1000,
                    }
                ],
                "context": {"application": "test_app", "language": "fr"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending_validation"
        assert len(data["detectedFields"]) == 6
        assert data["totalRows"] == 5

        # Vérifier que nom est en placeholder et email en encryption
        fields_by_name = {f["field"]: f for f in data["detectedFields"]}
        assert fields_by_name["nom"]["recommendedStrategy"] == "placeholder"
        assert fields_by_name["email"]["recommendedStrategy"] == "encryption"

    def test_full_flow_detect_then_execute(self):
        # Étape 1 : Détection
        detect_response = self.client.post(
            "/anonymisation/detect",
            json={
                "requestId": "test-002",
                "userId": "user-1",
                "conversationId": "conv-1",
                "message": "Anonymiser les données clients",
                "files": [
                    {
                        "fileId": "file-001",
                        "name": "clients.xlsx",
                        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "size": 1000,
                    }
                ],
                "context": {"application": "test_app", "language": "fr"},
            },
        )
        assert detect_response.status_code == 200

        # Étape 2 : Exécution complète (anonymise + LLM + dé-anonymise)
        exec_response = self.client.post(
            "/anonymisation/execute",
            json={
                "requestId": "test-002",
                "userId": "user-1",
                "conversationId": "conv-1",
                "targetLlm": "claude-sonnet-4-6",
                "validatedFields": [
                    {"field": "nom", "category": "NOM", "strategy": "placeholder"},
                    {"field": "prenom", "category": "NOM", "strategy": "placeholder"},
                    {"field": "email", "category": "EMAIL", "strategy": "encryption"},
                    {
                        "field": "telephone",
                        "category": "TELEPHONE",
                        "strategy": "placeholder",
                    },
                ],
            },
        )
        assert exec_response.status_code == 200
        data = exec_response.json()
        assert data["status"] == "completed"
        assert data["conversationId"] == "conv-1"
        # La réponse est dé-anonymisée (le mock retourne "[NOM_1]" → remplacé par "Dupont")
        assert "response" in data
        assert data["stats"]["fieldsAnonymized"] == 4
        assert data["stats"]["strategies"]["placeholder"] == 3
        assert data["stats"]["strategies"]["encryption"] == 1

        # Vérifier le fichier anonymisé (toujours sauvé côté serveur)
        anonymized_df = pd.read_excel(data["anonymizedFilePath"])
        assert anonymized_df["nom"].iloc[0] == "[NOM_1]"
        assert anonymized_df["email"].iloc[0] != "jean.dupont@mail.com"
        assert anonymized_df["montant_achat"].iloc[0] == 150.00

    def test_execute_without_detect(self):
        response = self.client.post(
            "/anonymisation/execute",
            json={
                "requestId": "unknown-id",
                "userId": "user-1",
                "conversationId": "conv-1",
                "targetLlm": "claude-sonnet-4-6",
                "validatedFields": [],
            },
        )
        assert response.status_code == 404


# ── Tests LLM Router ────────────────────────────────────────────────


class TestLlmRouter:
    def test_resolve_provider(self):
        assert resolve_provider("claude-sonnet-4-6") == "anthropic"
        assert resolve_provider("gpt-4o") == "openai"
        assert resolve_provider("o4-mini") == "openai"
        with pytest.raises(ValueError, match="non reconnu"):
            resolve_provider("llama-3")

    def test_deanonymize_placeholders(self):
        text = "Le client [NOM_1] habite à [ADRESSE_1] et gagne 3000 EUR."
        mappings = {
            "placeholder_mappings": {
                "NOM": {"[NOM_1]": "Vincent Dupont"},
                "ADRESSE": {"[ADRESSE_1]": "12 rue de la Paix, Paris"},
            },
        }
        result = deanonymize(text, mappings)
        assert result == "Le client Vincent Dupont habite à 12 rue de la Paix, Paris et gagne 3000 EUR."

    def test_deanonymize_encryption(self):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(b"secret@mail.com").decode()

        text = f"Son email est {encrypted}."
        mappings = {
            "placeholder_mappings": {},
            "encryption_key": key.decode(),
        }
        result = deanonymize(text, mappings)
        assert result == "Son email est secret@mail.com."

    def test_deanonymize_mixed(self):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        fernet = Fernet(key)
        encrypted_iban = fernet.encrypt(b"FR76 3000 6000 01").decode()

        text = f"[NOM_1] a pour IBAN {encrypted_iban}."
        mappings = {
            "placeholder_mappings": {
                "NOM": {"[NOM_1]": "Dupont"},
            },
            "encryption_key": key.decode(),
        }
        result = deanonymize(text, mappings)
        assert result == "Dupont a pour IBAN FR76 3000 6000 01."
