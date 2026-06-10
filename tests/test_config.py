"""Tests for env-var configuration (SPEC.md §10, §14)."""

import pytest

from domovoy.config import Config, ConfigError


def base_env(**overrides):
    env = {"BOT_TOKEN": "123:abc", "COORDINATOR_IDS": "111,222"}
    env.update(overrides)
    return env


class TestConfig:
    def test_loads_from_env(self):
        cfg = Config.from_env(base_env())
        assert cfg.bot_token == "123:abc"
        assert cfg.coordinator_ids == {111, 222}

    def test_missing_token_raises(self):
        with pytest.raises(ConfigError):
            Config.from_env({"COORDINATOR_IDS": "1"})

    def test_empty_token_raises(self):
        with pytest.raises(ConfigError):
            Config.from_env(base_env(BOT_TOKEN="  "))

    def test_coordinators_optional(self):
        cfg = Config.from_env({"BOT_TOKEN": "123:abc"})
        assert cfg.coordinator_ids == set()

    def test_coordinator_ids_tolerate_spaces_and_blanks(self):
        cfg = Config.from_env(base_env(COORDINATOR_IDS=" 111 , ,222, "))
        assert cfg.coordinator_ids == {111, 222}

    def test_invalid_coordinator_ids_raise(self):
        with pytest.raises(ConfigError):
            Config.from_env(base_env(COORDINATOR_IDS="111,abc"))

    def test_defaults(self):
        cfg = Config.from_env(base_env())
        assert cfg.db_path == "data/domovoy.db"
        assert cfg.digest_time == "09:00"
        assert cfg.tz == "UTC"

    def test_overrides(self):
        cfg = Config.from_env(
            base_env(DB_PATH="/data/bot.db", DIGEST_TIME="10:30", TZ="Europe/Belgrade")
        )
        assert cfg.db_path == "/data/bot.db"
        assert cfg.digest_time == "10:30"
        assert cfg.tz == "Europe/Belgrade"

    def test_invalid_digest_time_raises(self):
        with pytest.raises(ConfigError):
            Config.from_env(base_env(DIGEST_TIME="25:99"))

    def test_invalid_tz_raises(self):
        with pytest.raises(ConfigError):
            Config.from_env(base_env(TZ="Mars/Olympus"))

    def test_is_coordinator(self):
        cfg = Config.from_env(base_env())
        assert cfg.is_coordinator(111)
        assert not cfg.is_coordinator(999)
