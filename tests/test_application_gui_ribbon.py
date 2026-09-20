from rc_bridge.application.gui_ribbon import (
    RibbonField,
    RibbonSection,
    _capture_shared_values,
    _restore_shared_values,
    _ribbon_field_keys,
)


class _FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_ribbon_transaction_helpers_restore_cancelled_values() -> None:
    sections = (
        RibbonSection(
            "Geometry",
            (
                RibbonField("name", "Name"),
                RibbonField("deck_width", "Deck width"),
                RibbonField("enabled", "Enabled", kind="bool"),
            ),
        ),
    )
    string_keys, bool_keys = _ribbon_field_keys(sections)
    string_vars = {
        "name": _FakeVar("Original"),
        "deck_width": _FakeVar("11.0"),
    }
    bool_vars = {"enabled": _FakeVar(True)}

    string_snapshot, bool_snapshot = _capture_shared_values(
        string_vars,
        bool_vars,
        string_keys=string_keys,
        bool_keys=bool_keys,
    )

    string_vars["name"].set("Cancelled edit")
    string_vars["deck_width"].set("99.0")
    bool_vars["enabled"].set(False)

    _restore_shared_values(
        string_vars,
        bool_vars,
        string_values=string_snapshot,
        bool_values=bool_snapshot,
    )

    assert string_vars["name"].get() == "Original"
    assert string_vars["deck_width"].get() == "11.0"
    assert bool_vars["enabled"].get() is True
