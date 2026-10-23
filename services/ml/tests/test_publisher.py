"""Camera-event identities without a broker, videos, or model loading."""

from uuid import UUID

from app.publisher import MqttPublisher


def test_distinct_crossings_get_distinct_ids_even_with_reused_track_and_timestamp(monkeypatch):
    publisher = MqttPublisher(host="unused.invalid")
    published = []
    monkeypatch.setattr(publisher, "_publish", lambda topic, payload, **kwargs: published.append(payload))
    for _ in range(2):
        publisher.publish_event("A", "in", 1, "car", 0.9, ts=10.0)
    assert len({payload["event_id"] for payload in published}) == 2
    assert all(UUID(payload["event_id"]).version == 4 for payload in published)


def test_application_retry_can_preserve_the_crossing_id(monkeypatch):
    publisher = MqttPublisher(host="unused.invalid")
    published = []
    monkeypatch.setattr(publisher, "_publish", lambda topic, payload, **kwargs: published.append(payload))
    for _ in range(2):
        publisher.publish_event("A", "in", 1, "car", 0.9, ts=10.0, event_id="same-crossing")
    assert published[0] == published[1]
    assert published[0]["event_id"] == "same-crossing"
