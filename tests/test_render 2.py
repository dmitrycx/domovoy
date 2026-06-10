"""Tests for bilingual rendering (SPEC.md §5.4, §8)."""

from datetime import datetime, timezone

from domovoy.models import Request, Status
from domovoy.render import (
    age_days,
    is_stale,
    render_card,
    render_list,
    render_list_line,
    truncate,
    vote_button_text,
)

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def make_request(**overrides) -> Request:
    defaults = dict(
        id=12,
        group_chat_id=-100123,
        card_chat_id=None,
        card_msg_id=None,
        author_id=42,
        author_name="Dmitry",
        description="Broken light at the main gate",
        photo_file_id=None,
        status=Status.OPEN,
        owner=None,
        created_at="2026-03-08T10:00:00+00:00",
        updated_at="2026-06-09T10:00:00+00:00",
        deleted=False,
        votes=12,
    )
    defaults.update(overrides)
    return Request(**defaults)


class TestHelpers:
    def test_age_days(self):
        assert age_days("2026-03-08T10:00:00+00:00", NOW) == 94

    def test_age_days_same_day(self):
        assert age_days("2026-06-10T09:00:00+00:00", NOW) == 0

    def test_truncate_short_text_unchanged(self):
        assert truncate("short", 10) == "short"

    def test_truncate_long_text(self):
        result = truncate("a" * 50, 40)
        assert len(result) == 40
        assert result.endswith("…")

    def test_vote_button_text(self):
        assert vote_button_text(12) == "👍 12"


class TestStale:
    def test_open_request_not_updated_for_7_days_is_stale(self):
        req = make_request(updated_at="2026-06-01T10:00:00+00:00")
        assert is_stale(req, NOW) is True

    def test_recently_updated_is_not_stale(self):
        req = make_request(updated_at="2026-06-09T10:00:00+00:00")
        assert is_stale(req, NOW) is False

    def test_done_request_is_never_stale(self):
        req = make_request(
            status=Status.DONE, updated_at="2026-01-01T10:00:00+00:00"
        )
        assert is_stale(req, NOW) is False


class TestRenderCard:
    def test_card_contains_all_parts(self):
        card = render_card(make_request(), now=NOW)
        assert "#12" in card
        assert "Open / Открыта" in card
        assert "Broken light at the main gate" in card
        assert "Dmitry" in card
        assert "2026-03-08" in card
        assert "94" in card  # age in days
        assert "Owner / Ответственный: —" in card

    def test_card_shows_owner_when_assigned(self):
        card = render_card(make_request(owner="Ivan"), now=NOW)
        assert "Owner / Ответственный: Ivan" in card

    def test_card_status_bilingual_progress(self):
        card = render_card(make_request(status=Status.PROGRESS), now=NOW)
        assert "In progress / В работе" in card

    def test_card_status_bilingual_wontfix(self):
        card = render_card(make_request(status=Status.WONTFIX), now=NOW)
        assert "Won't fix / Закрыто" in card

    def test_card_flags_stale(self):
        req = make_request(updated_at="2026-05-01T10:00:00+00:00")
        card = render_card(req, now=NOW)
        assert "🔴" in card

    def test_fresh_card_has_no_stale_flag(self):
        card = render_card(make_request(), now=NOW)
        assert "🔴" not in card


class TestRenderList:
    def test_line_contains_fields(self):
        line = render_list_line(make_request(owner="Ivan"), now=NOW)
        assert "#12" in line
        assert "👍12" in line.replace("👍 ", "👍")
        assert "Broken light" in line
        assert "94" in line
        assert "Ivan" in line

    def test_line_truncates_long_description(self):
        req = make_request(description="x" * 100)
        line = render_list_line(req, now=NOW)
        assert "x" * 100 not in line

    def test_list_renders_header_and_lines(self):
        text = render_list([make_request(), make_request(id=13)], now=NOW)
        assert "#12" in text
        assert "#13" in text

    def test_empty_open_list_is_bilingual(self):
        text = render_list([], now=NOW)
        assert "No open requests" in text
        assert "Нет открытых заявок" in text

    def test_empty_done_list_is_bilingual(self):
        text = render_list([], now=NOW, done=True)
        assert "No resolved requests" in text
