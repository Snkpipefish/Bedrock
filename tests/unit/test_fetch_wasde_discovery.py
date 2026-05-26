"""Regression: WASDE URL-discovery må fange revisjons-suffix (`vN`)."""

from __future__ import annotations

from unittest.mock import patch

from bedrock.fetch.wasde import _collect_xml_paths_from_index

_FAKE_INDEX_HTML = """
<html><body>
  <a href="/sites/default/release-files/795903/wasde0526v2.xml">May 12 2026 (v2)</a>
  <a href="/sites/default/release-files/795855/wasde0426.xml">April 9 2026</a>
  <a href="/sites/default/release-files/3t945q76s/z890tt821/8336k1738/wasde0925.xml">Sept 12 2025</a>
  <a href="/sites/default/release-files/795722/wasde0126.xml">Jan 12 2026</a>
</body></html>
"""


class _FakeResp:
    text = _FAKE_INDEX_HTML

    def raise_for_status(self) -> None:
        return None


def test_collect_includes_revision_suffix() -> None:
    with patch("bedrock.fetch.wasde.requests.get", return_value=_FakeResp()):
        paths = _collect_xml_paths_from_index(max_pages=1)
    assert "/sites/default/release-files/795903/wasde0526v2.xml" in paths
    assert "/sites/default/release-files/795855/wasde0426.xml" in paths
    assert "/sites/default/release-files/795722/wasde0126.xml" in paths
    # Eldre dypere-nested URL skal også plukkes opp
    assert any("3t945q76s" in p for p in paths)
