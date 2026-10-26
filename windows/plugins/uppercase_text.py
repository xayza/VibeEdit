"""Example plugin: uppercase a text item's text."""


def register():
    def transform_text(project, item_id):
        _, item = project.item(item_id)
        if "text" not in item:
            raise ValueError("Item has no text field")
        item["text"] = str(item["text"]).upper()
        return item

    return {"name": "uppercase_text",
            "description": "Uppercase a text item's text.",
            "transform_text": transform_text}
