"""
Unit tests for the feed-fetching fallback chain in fetch_locations.py:
direct fetch -> rss2json.com proxy -> allorigins.win proxy. Run with:
    pytest test_fetch_locations.py
(requires pytest, not listed in requirements.txt since it's dev-only —
install separately: pip install pytest)
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from fetch_locations import (
    fetch_feed_posts,
    fetch_feed_posts_via_allorigins,
    fetch_feed_posts_via_proxy,
    fetch_feed_xml,
    parse_feed_xml,
)

FEED_URL = "https://example.substack.com/feed"

SAMPLE_XML = """<?xml version="1.0"?>
<rss><channel>
<item>
<title><![CDATA[Post one]]></title>
<link>https://example.substack.com/p/one</link>
<pubDate>Mon, 01 Jun 2026 09:00:00 GMT</pubDate>
<content:encoded><![CDATA[<p>We sailed into Ruhnu.</p>]]></content:encoded>
</item>
</channel></rss>
"""


def _response(status_code=200, text="", json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error", response=resp)
    else:
        resp.raise_for_status.side_effect = None
    return resp


# --- direct fetch --------------------------------------------------------

def test_fetch_feed_xml_succeeds_first_try():
    ok = _response(200, text=SAMPLE_XML)
    with patch("fetch_locations.requests.get", return_value=ok) as get:
        result = fetch_feed_xml(FEED_URL)
    assert result == SAMPLE_XML
    assert get.call_count == 1


def test_fetch_feed_xml_retries_403_then_succeeds():
    blocked = _response(403, text="Just a moment...")
    ok = _response(200, text=SAMPLE_XML)
    with patch("fetch_locations.requests.get", side_effect=[blocked, ok]), \
         patch("fetch_locations.time.sleep"):
        result = fetch_feed_xml(FEED_URL)
    assert result == SAMPLE_XML


def test_fetch_feed_xml_raises_with_context_after_exhausting_retries():
    blocked = _response(403, text="Just a moment...")
    with patch("fetch_locations.requests.get", return_value=blocked), \
         patch("fetch_locations.time.sleep"):
        with pytest.raises(requests.RequestException) as exc_info:
            fetch_feed_xml(FEED_URL)
    assert "status=403" in str(exc_info.value)


def test_parse_feed_xml_extracts_posts():
    posts = parse_feed_xml(SAMPLE_XML)
    assert len(posts) == 1
    assert posts[0]["title"] == "Post one"
    assert posts[0]["url"] == "https://example.substack.com/p/one"
    assert posts[0]["text"] == "We sailed into Ruhnu."


# --- rss2json.com proxy ---------------------------------------------------

def test_proxy_succeeds_first_try():
    ok = _response(200, json_data={
        "status": "ok",
        "items": [{"title": "T", "link": "https://x/p", "pubDate": "d", "content": "<p>hi</p>"}],
    })
    with patch("fetch_locations.requests.get", return_value=ok) as get:
        posts = fetch_feed_posts_via_proxy(FEED_URL)
    assert posts == [{"title": "T", "url": "https://x/p", "pub_date": "d", "text": "hi"}]
    assert get.call_count == 1


def test_proxy_retries_transient_500_then_succeeds():
    failing = _response(500, text="Internal Server Error")
    ok = _response(200, json_data={
        "status": "ok",
        "items": [{"title": "T", "link": "https://x/p", "pubDate": "d", "content": "hi"}],
    })
    with patch("fetch_locations.requests.get", side_effect=[failing, ok]), \
         patch("fetch_locations.time.sleep") as sleep:
        posts = fetch_feed_posts_via_proxy(FEED_URL)
    assert len(posts) == 1
    sleep.assert_called_once()


def test_proxy_raises_after_exhausting_retries():
    failing = _response(500, text="Internal Server Error")
    with patch("fetch_locations.requests.get", return_value=failing), \
         patch("fetch_locations.time.sleep"):
        with pytest.raises(requests.RequestException):
            fetch_feed_posts_via_proxy(FEED_URL)


def test_proxy_retries_on_error_status_in_json_body():
    error_body = _response(200, json_data={"status": "error", "message": "rate limited"})
    ok = _response(200, json_data={
        "status": "ok",
        "items": [{"title": "T", "link": "https://x/p", "pubDate": "d", "content": "hi"}],
    })
    with patch("fetch_locations.requests.get", side_effect=[error_body, ok]), \
         patch("fetch_locations.time.sleep"):
        posts = fetch_feed_posts_via_proxy(FEED_URL)
    assert len(posts) == 1


# --- allorigins.win proxy --------------------------------------------------

def test_allorigins_succeeds_first_try():
    ok = _response(200, text=SAMPLE_XML)
    with patch("fetch_locations.requests.get", return_value=ok) as get:
        posts = fetch_feed_posts_via_allorigins(FEED_URL)
    assert len(posts) == 1
    assert posts[0]["url"] == "https://example.substack.com/p/one"
    assert get.call_count == 1


def test_allorigins_retries_transient_failure_then_succeeds():
    failing = _response(500, text="Internal Server Error")
    ok = _response(200, text=SAMPLE_XML)
    with patch("fetch_locations.requests.get", side_effect=[failing, ok]), \
         patch("fetch_locations.time.sleep") as sleep:
        posts = fetch_feed_posts_via_allorigins(FEED_URL)
    assert len(posts) == 1
    sleep.assert_called_once()


def test_allorigins_raises_after_exhausting_retries():
    failing = _response(500, text="Internal Server Error")
    with patch("fetch_locations.requests.get", return_value=failing), \
         patch("fetch_locations.time.sleep"):
        with pytest.raises(requests.RequestException):
            fetch_feed_posts_via_allorigins(FEED_URL)


# --- overall fallback chain ------------------------------------------------

def test_fetch_feed_posts_uses_direct_result_when_it_succeeds():
    with patch("fetch_locations.fetch_feed_xml", return_value=SAMPLE_XML), \
         patch("fetch_locations.fetch_feed_posts_via_proxy") as proxy, \
         patch("fetch_locations.fetch_feed_posts_via_allorigins") as allorigins:
        posts = fetch_feed_posts(FEED_URL)
    assert len(posts) == 1
    proxy.assert_not_called()
    allorigins.assert_not_called()


def test_fetch_feed_posts_falls_back_to_proxy_when_direct_fails():
    proxy_posts = [{"title": "p", "url": "u", "pub_date": "d", "text": "t"}]
    with patch("fetch_locations.fetch_feed_xml", side_effect=requests.RequestException("blocked")), \
         patch("fetch_locations.fetch_feed_posts_via_proxy", return_value=proxy_posts) as proxy, \
         patch("fetch_locations.fetch_feed_posts_via_allorigins") as allorigins:
        posts = fetch_feed_posts(FEED_URL)
    assert posts == proxy_posts
    proxy.assert_called_once()
    allorigins.assert_not_called()


def test_fetch_feed_posts_falls_back_to_allorigins_when_direct_and_proxy_fail():
    allorigins_posts = [{"title": "p", "url": "u", "pub_date": "d", "text": "t"}]
    with patch("fetch_locations.fetch_feed_xml", side_effect=requests.RequestException("blocked")), \
         patch("fetch_locations.fetch_feed_posts_via_proxy",
               side_effect=requests.RequestException("proxy down")), \
         patch("fetch_locations.fetch_feed_posts_via_allorigins", return_value=allorigins_posts) as allorigins:
        posts = fetch_feed_posts(FEED_URL)
    assert posts == allorigins_posts
    allorigins.assert_called_once()


def test_fetch_feed_posts_raises_when_all_three_fail():
    with patch("fetch_locations.fetch_feed_xml", side_effect=requests.RequestException("blocked")), \
         patch("fetch_locations.fetch_feed_posts_via_proxy",
               side_effect=requests.RequestException("proxy down")), \
         patch("fetch_locations.fetch_feed_posts_via_allorigins",
               side_effect=requests.RequestException("allorigins down")):
        with pytest.raises(requests.RequestException):
            fetch_feed_posts(FEED_URL)
