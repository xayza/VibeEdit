"""Example plugin: set a clip's colour preset to vivid."""


def register():
    def apply_color(project, item_id):
        return project.set_color(item_id, preset="vivid")

    return {"name": "vivid_color",
            "description": "Set a clip's colour preset to vivid.",
            "apply_color": apply_color}
