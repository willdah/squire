"""Tests for SSH key management."""

import stat
from unittest.mock import patch

import pytest

from squire.system.keys import delete_key, generate_key, get_key_path, get_public_key


@pytest.fixture
def keys_dir(tmp_path):
    """Redirect key storage to a temp directory."""
    d = tmp_path / "keys"
    with patch("squire.system.keys._keys_dir", return_value=d):
        yield d


class TestGenerateKey:
    def test_creates_key_pair(self, keys_dir):
        private_path, public_text = generate_key("test-host")
        assert private_path.exists()
        assert private_path.name == "test-host"
        pub_path = keys_dir / "test-host.pub"
        assert pub_path.exists()
        assert public_text.startswith("ssh-ed25519 ")
        assert "squire-managed:test-host" in public_text

    def test_private_key_permissions(self, keys_dir):
        private_path, _ = generate_key("test-host")
        mode = private_path.stat().st_mode
        assert stat.S_IMODE(mode) == 0o600

    def test_keys_dir_created_with_correct_permissions(self, keys_dir):
        generate_key("test-host")
        mode = keys_dir.stat().st_mode
        assert stat.S_IMODE(mode) == 0o700

    def test_public_key_permissions(self, keys_dir):
        generate_key("test-host")
        pub_path = keys_dir / "test-host.pub"
        mode = pub_path.stat().st_mode
        assert stat.S_IMODE(mode) == 0o644

    def test_raises_on_duplicate(self, keys_dir):
        generate_key("test-host")
        with pytest.raises(FileExistsError):
            generate_key("test-host")


class TestGetKeyPath:
    def test_returns_path_when_exists(self, keys_dir):
        generate_key("test-host")
        assert get_key_path("test-host") == keys_dir / "test-host"

    def test_returns_none_when_missing(self, keys_dir):
        assert get_key_path("nonexistent") is None


class TestGetPublicKey:
    def test_returns_public_key_text(self, keys_dir):
        _, expected_text = generate_key("test-host")
        assert get_public_key("test-host") == expected_text

    def test_returns_none_when_missing(self, keys_dir):
        assert get_public_key("nonexistent") is None


class TestDeleteKey:
    def test_deletes_existing_key(self, keys_dir):
        generate_key("test-host")
        assert delete_key("test-host") is True
        assert not (keys_dir / "test-host").exists()
        assert not (keys_dir / "test-host.pub").exists()

    def test_returns_false_for_missing(self, keys_dir):
        assert delete_key("nonexistent") is False
