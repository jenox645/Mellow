def test_record_and_stats(client):
    from mellow import analytics
    analytics.record_download({
        'url': 'https://youtube.com/watch?v=test',
        'title': 'Test Video',
        'platform': 'youtube',
        'format': 'video',
        'quality': '1080p',
        'container': 'mp4',
        'status': 'success',
        'file_size_bytes': 50_000_000,
        'duration_seconds': 120,
    })
    stats = analytics.get_stats('30d')
    assert stats['total_downloads'] >= 1


def test_history_pagination(client):
    r = client.get('/api/history?limit=5&offset=0')
    assert r.status_code == 200
    data = r.get_json()
    assert 'items' in data or isinstance(data, list)


def test_analytics_query_select_only(client):
    r = client.post('/api/analytics/query', json={'sql': 'SELECT 1 AS n'})
    assert r.status_code == 200


def test_analytics_query_drop_returns_result(client):
    r = client.post('/api/analytics/query', json={'sql': 'DROP TABLE IF EXISTS nonexistent_xyz'})
    assert r.status_code == 200


def test_export_csv(client):
    r = client.get('/api/analytics/export')
    assert r.status_code == 200
    assert b'url' in r.data.lower() or b'title' in r.data.lower()


def test_analytics_query_allows_leading_comments_but_not_writes(client):
    """A "-- comment" line before SELECT was refused as not a SELECT."""
    ok = client.post('/api/analytics/query', json={'sql': '-- how many?\n/* all */ SELECT COUNT(*) FROM downloads'}).get_json()
    assert ok['error'] is None and ok['rows'] == [[0]]
    for sql in ('-- sneaky\nDELETE FROM downloads', '/* x */ DROP TABLE downloads', '-- only a comment'):
        assert client.post('/api/analytics/query', json={'sql': sql}).get_json()['error'], sql


def test_a_cancelled_download_is_not_a_failure(client):
    import datetime

    from mellow import analytics
    for status in ['success', 'success', 'success', 'error', 'cancelled', 'cancelled']:
        analytics.record_download({'url': 'https://example.com/v', 'title': 'v', 'platform': 'Other',
                                   'format': 'video', 'status': status})
    assert analytics.get_stats('30d')['success_rate'] == 75.0          # 3 of 4: the cancels don't count
    assert analytics.get_wrapped(datetime.date.today().year)['success_rate'] == 75.0


def test_only_cancelled_downloads_have_no_success_rate(client):
    from mellow import analytics
    analytics.record_download({'url': 'https://example.com/v', 'title': 'v', 'platform': 'Other',
                               'format': 'video', 'status': 'cancelled'})
    assert analytics.get_stats('30d')['success_rate'] is None


def test_purging_the_history_keeps_the_library(client):
    """PURGE wiped the library too (folders linked to playlists and their sync
    settings) while saying it deleted download records."""
    from mellow import analytics, config
    analytics.record_download({'url': 'https://youtu.be/aaaaaaaaaaa', 'title': 'Song', 'status': 'success'})
    analytics.upsert_library_entry({'id': 'e1', 'name': 'Chill', 'url': 'https://x/pl', 'folder': '/m',
                                    'folder_name': 'Chill'})
    config.update_config(lambda c: c.update(stat_overrides={'total_downloads': 99}))
    r = client.delete('/api/history', json={'all': True})
    assert r.get_json() == {'deleted': 1}
    assert analytics.get_history() == []
    assert [e['id'] for e in analytics.get_library_entries()] == ['e1']
    assert config.load_config()['stat_overrides'] == {}
