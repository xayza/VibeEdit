import VibeEditProject

extension CommandCatalog {
    /// VibeEdit itself: its version and whether a newer release is out (VibeEdit › Check for Updates…).
    static let appSpecs: [CommandSpec] = [
        CommandSpec(
            "app.version", .read,
            "This VibeEdit's version and build, how it was installed (homebrew, direct, app-store, development) and "
                + "the plugin API it offers, like About VibeEdit."),
        CommandSpec(
            "app.update-check", .read,
            "Ask GitHub for the latest VibeEdit release, like VibeEdit › Check for Updates…. Returns this version, the "
                + "latest release (version, page, notes) when it is newer, and how to update: the Homebrew command or "
                + "the release page, and canUpdateNow when app update can install it. Never installs anything; App "
                + "Store and TestFlight copies are not checked."),
        CommandSpec(
            "app.update", .privileged,
            "Update a Homebrew copy of VibeEdit to the release app update-check found, like Update Now in Software "
                + "Update; the user approves it in the app first. Homebrew downloads the release while VibeEdit runs, "
                + "then VibeEdit saves the project, quits, upgrades (brew upgrade --cask vibeedit) and opens again. A "
                + "failure keeps VibeEdit running: app update-check reports it as installError. Downloaded copies "
                + "update from the release page.",
            execution: .approval),
    ]
}
