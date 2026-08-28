"""EmbedConfig/RetrieveConfig/JudgeConfig -- typed alternative to scattered
env-var reads in embed/retrieve/judge resolvers. Precedence under test:
explicit kwarg > cfg field > env var > default constant.
"""
from __future__ import annotations

import pytest

from veramynd_parser.config import EmbedConfig, JudgeConfig, RetrieveConfig
from veramynd_parser.embed.runner import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_STANDARDS_COLLECTION,
    resolve_embedding_model,
    resolve_qdrant_settings,
    resolve_standards_qdrant_settings,
)
from veramynd_parser.judge.pipeline import (
    DEFAULT_ESCALATE_MODEL,
    DEFAULT_JUDGE_MODEL,
    resolve_escalate_model,
    resolve_judge_model,
)
from veramynd_parser.retrieve.rerank import (
    DEFAULT_RERANK_MODEL,
    resolve_rerank_model,
)


@pytest.fixture(autouse=True)
def _clear_relevant_env(monkeypatch):
    for var in (
        "OPENAI_EMBEDDING_MODEL",
        "QDRANT_URL",
        "QDRANT_API_KEY",
        "QDRANT_PATH",
        "QDRANT_COLLECTION",
        "QDRANT_STANDARDS_COLLECTION",
        "QDRANT_ALLOW_INSECURE",
        "RERANK_MODEL",
        "JUDGE_MODEL",
        "JUDGE_ESCALATE_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)


class TestEmbeddingModel:
    def test_default_with_no_cfg_no_env(self):
        assert resolve_embedding_model() == DEFAULT_EMBEDDING_MODEL

    def test_cfg_field_overrides_default(self):
        cfg = EmbedConfig(embedding_model="text-embedding-3-small")
        assert resolve_embedding_model(cfg=cfg) == "text-embedding-3-small"

    def test_env_wins_over_cfg_absent(self, monkeypatch):
        monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "env-model")
        assert resolve_embedding_model() == "env-model"

    def test_explicit_wins_over_cfg_and_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "env-model")
        cfg = EmbedConfig(embedding_model="cfg-model")
        assert resolve_embedding_model("explicit-model", cfg=cfg) == "explicit-model"

    def test_cfg_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "env-model")
        cfg = EmbedConfig(embedding_model="cfg-model")
        assert resolve_embedding_model(cfg=cfg) == "cfg-model"


class TestQdrantSettings:
    def test_cfg_path_used_when_no_explicit_or_env(self):
        cfg = EmbedConfig(qdrant_path="/tmp/my_qdrant")
        result = resolve_qdrant_settings(cfg=cfg)
        assert result["path"].endswith("my_qdrant")

    def test_explicit_path_wins_over_cfg(self):
        cfg = EmbedConfig(qdrant_path="/tmp/cfg_path")
        result = resolve_qdrant_settings(path="/tmp/explicit_path", cfg=cfg)
        assert result["path"].endswith("explicit_path")

    def test_cfg_collection_used(self):
        cfg = EmbedConfig(qdrant_collection="my_standards")
        assert resolve_qdrant_settings(cfg=cfg)["collection"] == "my_standards"

    def test_default_collection_with_no_cfg(self):
        assert resolve_qdrant_settings()["collection"] == DEFAULT_STANDARDS_COLLECTION

    def test_cfg_allows_insecure_http_with_key(self):
        cfg = EmbedConfig(qdrant_allow_insecure=True)
        result = resolve_qdrant_settings(
            url="http://qdrant.example.com", api_key="k", cfg=cfg
        )
        assert result["api_key"] == "k"

    def test_insecure_http_with_key_still_blocked_without_cfg_flag(self):
        from veramynd_parser.embed.runner import EmbedError

        with pytest.raises(EmbedError):
            resolve_qdrant_settings(url="http://qdrant.example.com", api_key="k")


class TestStandardsQdrantSettings:
    def test_cfg_standards_collection_used(self):
        cfg = EmbedConfig(qdrant_standards_collection="my_standards")
        assert resolve_standards_qdrant_settings(cfg=cfg)["collection"] == "my_standards"

    def test_default_standards_collection_with_no_cfg(self):
        assert (
            resolve_standards_qdrant_settings()["collection"] == DEFAULT_STANDARDS_COLLECTION
        )

    def test_cfg_general_collection_does_not_leak_into_standards(self):
        cfg = EmbedConfig(qdrant_collection="my_general")
        assert resolve_standards_qdrant_settings(cfg=cfg)["collection"] == DEFAULT_STANDARDS_COLLECTION


class TestRerankModel:
    def test_default_with_no_cfg_no_env(self):
        assert resolve_rerank_model() == DEFAULT_RERANK_MODEL

    def test_cfg_field_overrides_default(self):
        cfg = RetrieveConfig(rerank_model="cross-encoder/other")
        assert resolve_rerank_model(cfg=cfg) == "cross-encoder/other"

    def test_explicit_wins_over_cfg(self):
        cfg = RetrieveConfig(rerank_model="cfg-model")
        assert resolve_rerank_model("explicit-model", cfg=cfg) == "explicit-model"


class TestJudgeModels:
    def test_default_judge_model_with_no_cfg_no_env(self):
        assert resolve_judge_model() == DEFAULT_JUDGE_MODEL

    def test_cfg_judge_model_overrides_default(self):
        cfg = JudgeConfig(judge_model="gpt-x")
        assert resolve_judge_model(cfg=cfg) == "gpt-x"

    def test_default_escalate_model_with_no_cfg_no_env(self):
        assert resolve_escalate_model() == DEFAULT_ESCALATE_MODEL

    def test_cfg_escalate_model_overrides_default(self):
        cfg = JudgeConfig(escalate_model="gpt-y")
        assert resolve_escalate_model(cfg=cfg) == "gpt-y"

    def test_explicit_wins_over_cfg_for_judge_model(self):
        cfg = JudgeConfig(judge_model="cfg-model")
        assert resolve_judge_model("explicit-model", cfg=cfg) == "explicit-model"


class TestConfigModelsRejectUnknownFields:
    def test_embed_config_forbids_typo_field(self):
        with pytest.raises(Exception):
            EmbedConfig(embeding_model="typo")

    def test_retrieve_config_forbids_typo_field(self):
        with pytest.raises(Exception):
            RetrieveConfig(rernak_model="typo")

    def test_judge_config_forbids_typo_field(self):
        with pytest.raises(Exception):
            JudgeConfig(judg_model="typo")
