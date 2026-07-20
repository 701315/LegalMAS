from services.playbooks.diff import PlaybookVersionDiffService


def test_diff_detects_changes():
    class Dummy:
        def __init__(self, source):
            self.source_payload = source

    base = Dummy({"profile": "core", "bundles": ["a"]})
    other = Dummy({"profile": "full", "bundles": ["a"]})

    service = PlaybookVersionDiffService()
    changes = service.diff(base, other)

    assert len(changes) == 1
    assert changes[0]["field"] == "profile"


    