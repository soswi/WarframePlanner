"""Values a brand-new database starts with.

Kept apart from `config` so the two can be reasoned about separately: `config`
answers "where does this run", these answer "what does it contain on day one".
Changing anything here affects only fresh installs unless a migration in
`storage.migrations` is added to carry existing ones forward.
"""

from __future__ import annotations

#: Ordered (value, colour) pairs per definition kind.
DEFAULT_DEFINITIONS: dict[str, list[tuple[str, str]]] = {
    "status": [
        ("Done", "#39fe74"),
        ("In Progress", "#4d91fe"),
        ("Stuck", "#ec4657"),
        ("Active", "#1ce9db"),
    ],
    "priority": [
        ("Very High", "#ec4657"),
        ("High", "#fda817"),
        ("Medium", "#ffc370"),
        ("Low", "#9ac4fe"),
    ],
    "category": [
        ("Void Fissure", "#fda817"),
        ("Credits", "#0f97ff"),
        ("Platinum", "#c7eeff"),
        ("Resources", "#9ea39e"),
        ("Build", "#39fe74"),
        ("Standing", "#552ef5"),
        ("Preparation", "#e64777"),
        ("Event", "#f472b6"),
        ("Clan", "#c084fc"),
        ("Alliance", "#fe4876"),
        ("Level Up", "#20ee9f"),
        ("Mastery Rank", "#e879f9"),
        ("Kuva", "#ff2e43"),
        ("Grind", "#8a14ff"),
    ],
}

DEFAULT_SETTINGS: dict[str, str] = {
    "done_status": "Done",
    "reset_status": "In Progress",
    "min_task_id": "1000",
    "theme": "zariman",
    "layout": "table",
    "enforce_dependency_gate": "true",
    # Status pinned to the front of every list. Empty disables the behaviour.
    "highlight_status": "Active",
    "board_group_by": "status",
    "board_card_size": "comfortable",
}
