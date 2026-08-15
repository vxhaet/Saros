import json

import pandas as pd
from cryptography.fernet import Fernet
from pathlib import Path

from .models import AnonymizationStrategy, EntityValidation, FieldValidation


class Anonymizer:
    def __init__(self, encryption_key: str | None = None):
        if encryption_key:
            self.key = encryption_key.encode()
        else:
            self.key = Fernet.generate_key()
        self.fernet = Fernet(self.key)
        self._placeholder_maps: dict[str, dict[str, str]] = {}

    def anonymize(
        self, df: pd.DataFrame, fields: list[FieldValidation]
    ) -> pd.DataFrame:
        result = df.copy()
        for field in fields:
            if field.field not in result.columns:
                continue
            if field.strategy == AnonymizationStrategy.PLACEHOLDER:
                result[field.field] = self._apply_placeholder(
                    result[field.field], field.category
                )
            elif field.strategy == AnonymizationStrategy.ENCRYPTION:
                result[field.field] = self._apply_encryption(result[field.field])
        return result

    def _apply_placeholder(
        self, series: pd.Series, category: str
    ) -> pd.Series:
        prefix = category.upper()
        value_map: dict[str, str] = {}
        counter = 0

        def replace(value):
            nonlocal counter
            str_val = str(value) if pd.notna(value) else ""
            if not str_val:
                return ""
            if str_val not in value_map:
                counter += 1
                value_map[str_val] = f"[{prefix}_{counter}]"
            return value_map[str_val]

        result = series.map(replace)
        # Stocke le mapping inverse : placeholder -> valeur originale
        self._placeholder_maps[prefix] = {v: k for k, v in value_map.items()}
        return result

    def _apply_encryption(self, series: pd.Series) -> pd.Series:
        cache: dict[str, str] = {}

        def encrypt(value):
            str_val = str(value) if pd.notna(value) else ""
            if not str_val:
                return ""
            if str_val not in cache:
                cache[str_val] = self.fernet.encrypt(str_val.encode()).decode()
            return cache[str_val]

        return series.map(encrypt)

    def anonymize_text(
        self, text: str, entities: list[EntityValidation]
    ) -> str:
        result = text
        # Trier par longueur décroissante pour remplacer les plus longs d'abord
        sorted_entities = sorted(entities, key=lambda e: len(e.value), reverse=True)
        for entity in sorted_entities:
            if entity.value not in result:
                continue
            if entity.strategy == AnonymizationStrategy.PLACEHOLDER:
                prefix = entity.category.upper()
                if prefix not in self._placeholder_maps:
                    self._placeholder_maps[prefix] = {}
                counter = len(self._placeholder_maps[prefix]) + 1
                placeholder = f"[{prefix}_{counter}]"
                self._placeholder_maps[prefix][placeholder] = entity.value
                result = result.replace(entity.value, placeholder)
            elif entity.strategy == AnonymizationStrategy.ENCRYPTION:
                encrypted = self.fernet.encrypt(entity.value.encode()).decode()
                result = result.replace(entity.value, encrypted)
        return result

    def get_mappings(self) -> dict:
        return {
            "placeholder_mappings": self._placeholder_maps,
            "encryption_key": self.key.decode(),
        }

    def save_mappings(self, output_path: str) -> str:
        mappings_path = str(
            Path(output_path).parent / f"mappings_{Path(output_path).stem}.json"
        )
        with open(mappings_path, "w", encoding="utf-8") as f:
            json.dump(self.get_mappings(), f, ensure_ascii=False, indent=2)
        return mappings_path
