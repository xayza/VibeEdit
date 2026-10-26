# 07 — Folder structure

This is the `bash-cut/` repository as it stands at HEAD. `Package.swift` declares every target; `project.yml`
(XcodeGen) only wraps the app bundle around them. Items marked *(planned)* do not exist yet. Do not create empty
folders to match a plan; add a folder when the first file needs it.

## Repository tree

```text
bash-cut/
├── AGENTS.md                      # instructions for agents developing the app
├── CLAUDE.md                      # @AGENTS.md
├── CONTRIBUTING.md                # build layout and one-file extension templates
├── README.md
├── CHANGELOG.md                   # [Unreleased] section, one line per meaningful change
├── Package.swift                  # single source of targets (app, CLI, MCP, libraries, tests, bench)
├── Package.resolved               # committed lockfile
├── project.yml                    # XcodeGen; VibeEdit.xcodeproj is generated and not committed
├── .swiftlint.yml  .swift-format  .editorconfig  .gitignore
│
├── .claude/  .agents/            # local agent rules and skills, gitignored (not in the repository)
│
├── Configs/
│   ├── Base.xcconfig  Debug.xcconfig  Release.xcconfig
│   └── Version.xcconfig           # MARKETING_VERSION, CURRENT_PROJECT_VERSION
│                                  # Secrets.xcconfig is optional and gitignored
│
├── VibeEdit/                       # app executable (product VibeEditApp)
│   ├── main.swift  AppDelegate.swift  Info.plist  VibeEdit.entitlements
│   ├── Core/
│   │   ├── Engine/                # library VibeEditEngine: CompositionBuilder (+ Audio/VideoCompositionLanes,
│   │   │                          # IntervalSweep, AssetCache, FileSignature, LUTCache), VibeEditCompositor,
│   │   │                          # RenderEngine, Exporter (+ ExportDestination, ExportSampleTransfer),
│   │   │                          # ExportPreset, TextRenderer, TimeMapping, MediaSource, ProxyManager,
│   │   │                          # AudioWaveform, AudioGainPlanner, CubeLUT, SpeedRampPlan,
│   │   │                          # SpeedRampAudioCache/Renderer, SpeedRampTimeStretch
│   │   ├── Storage/               # library VibeEditStorage: ProjectStorage, ProjectCreation,
│   │   │                          # ProjectFileMonitor, ExportHistoryStore
│   │   ├── Automation/            # library VibeEditAutomation: CommandSpec, CommandCatalog,
│   │   │                          # CommandRegistry, CommandLineParser, UIAction, UnixSocket, Wire,
│   │   │                          # AgentInstructions, MCPBridgeClient, DebugLog (+ DebugLogWriter),
│   │   │                          # ChatCommandSession, TimelineDryRun, AutomationOutputPath
│   │   ├── Agent/                 # library VibeEditAgent: AgentProvider (Claude, Codex, Shell),
│   │   │                          # AgentLaunch, AgentEnvironment, AgentSessionStore
│   │   ├── Plugins/               # library VibeEditPlugins: CapabilityService, CapabilityAdapter,
│   │   │                          # PluginOptionPolicy, PluginSecretStore
│   │   │   └── Capabilities/      # one adapter per capability (transcription, beats, loudness, voice)
│   │   ├── Services/              # library VibeEditDocument: AppServices, JobCenter, ExportQueue,
│   │   │                          # ExportPipeline, ProxyQueue, PreviewController (+ PreviewBuildPair,
│   │   │                          # PreviewSeekQueue, PreviewTiming, PlayerItemReadiness), ExportController,
│   │   │                          # FileSyncController, AutomationController, SettingsModel,
│   │   │                          # EditorUIState, ModalCenter, TimelineFormats
│   │   └── Document/              # app target: ProjectDocument, history, `commit`, command handlers
│   │                              # (ProjectDocument+<Area>.swift)
│   ├── Models/                    # small app-only value types
│   ├── ViewModels/                # @Observable models: agent dock, knowledge, Doctor, plugins, voice…
│   ├── Views/                     # SwiftUI/AppKit views, one file per screen or panel
│   └── Resources/
│       ├── Localizable.xcstrings  # English (development language) + Vietnamese
│       └── en.lproj/  vi.lproj/   # InfoPlist.strings, Localizable.strings
│
├── CLI/VibeEditCLI.swift           # executable `vibeedit` (swift-argument-parser)
├── MCPBridge/VibeEditMCP.swift     # executable `vibeedit-mcp` (MCP Swift SDK, stdio)
├── Tools/Bench/main.swift         # executable `vibeedit-bench`: engine benchmark on real footage
├── Tools/Fixtures/main.swift      # executable `vibeedit-fixtures`: writes the synthetic sample movie
│
├── Packages/
│   └── VibeEditCore/               # pure-logic package; `swift test` runs without Xcode
│       ├── Package.swift  Package.resolved
│       ├── Sources/
│       │   ├── VibeEditProject/    # Project, tracks/items, EditOperation + codec, history, validation,
│       │   │                      # layer rules, diff, review rules, SubRip, timeline-format protocols
│       │   ├── VibeEditPlugin/     # vibeedit.plugin/1 manifest, catalog, provider resolver, transport,
│       │   │                      # process runner
│       │   ├── VibeEditImport/     # legacy edl.json importer
│       │   └── VibeEditInterchange/  # OpenTimelineIO exporter
│       └── Tests/
│           ├── VibeEditProjectTests/  VibeEditPluginTests/
│           ├── VibeEditImportTests/   VibeEditInterchangeTests/
│           └── VibeEditProjectFixtures/  # shared projects and the apply→undo→redo helper
│
├── Tests/                         # one test target per app library
│   ├── VibeEditEngineTests/        # includes __Snapshots__/ golden frames
│   ├── VibeEditStorageTests/  VibeEditAutomationTests/  VibeEditAgentTests/
│   ├── VibeEditPluginsTests/  VibeEditDocumentTests/
│   └── VibeEditTestSupport/        # shared fixtures: generated media, scratch folders, synthetic audio
│
├── Fixtures/
│   ├── make-media.sh              # optional native AVFoundation sample in media/test.mp4
│   └── media/                     # generated, gitignored
│
├── scripts/
│   ├── generate-project.sh        # checks for XcodeGen, generates VibeEdit.xcodeproj
│   ├── verify.sh                  # build | test | lint | xcode [build|test] | perf
│   ├── run.sh                     # builds, signs and opens build/VibeEdit.app
│   ├── deploy-testflight.sh       # Mac App Store archive, uploaded to TestFlight
│   ├── build-release.sh           # Developer ID: archive, verify, notarize; zip + dmg (+ pkg) in build/release/
│   ├── create-dmg.sh              # dmg from a signed app (a build-release.sh step, also runnable alone)
│   ├── create-pkg.sh              # pkg from a signed app (likewise)
│   ├── render-app-icon.sh         # AppIcon.appiconset and the README logo, rendered from VibeEditLogo
│   ├── update-acknowledgements.py # VibeEdit/Models/Acknowledgements.swift: licenses shown in the About panel
│   ├── lib/                       # sourced helpers: common.sh (.env, version), signing.sh, notarize.sh
│   └── ci/                        # checks of the scripts themselves (test-script-lib.sh)
│
├── mockups/vibeedit-ui.html        # interactive UI mockup (reference only)
│
└── docs/
    ├── README.md                  # documentation index
    ├── guides/                    # automation.md (CLI/MCP commands), plugins.md (plugin API)
    ├── reference/                 # project-format.md (schema), third-party.md (dependencies, licenses)
    ├── status/                    # implementation.md, mockup-parity.md
    └── specs/                     # these documents, 00–10
```

Generated and ignored: `.build/`, `build/` (app bundle, `build/logs/`, Xcode derived data), `.swiftpm/`,
`VibeEdit.xcodeproj/`, `Fixtures/media/`.

### Planned

These appear in earlier drafts of this spec and are not in the repository yet:

- `Fixtures/workspace-mini/` (fake workspace with trimmed real `edl.json`) and `Fixtures/projects/` (sample and
  broken project files).
- A UI test target and a dedicated performance test target. Today `scripts/verify.sh perf` runs the engine tests
  with `VIBEEDIT_PERF=1`, and real-footage numbers come from `vibeedit-bench`.
- `scripts/install-cli.sh` (a `vibeedit` shim on `PATH`).
- Finer folders inside `Core/Engine` and `Views/` once those areas grow.

## Targets

`Package.swift` is the single source of targets. `project.yml` declares only what Xcode must own and links the
package's library products. `scripts/verify.sh xcode [build|test]` regenerates the project and builds or tests it.

| Target | Kind | Path | Notes |
|---|---|---|---|
| `VibeEdit` | executable (product `VibeEditApp`) | `VibeEdit/` | The app; excludes `Core/*` library folders. SwiftTerm is linked here only |
| `VibeEditEngine` | library | `VibeEdit/Core/Engine` | AVFoundation compositor, export, proxies, waveforms |
| `VibeEditStorage` | library | `VibeEdit/Core/Storage` | Project files, creation, monitoring, export history |
| `VibeEditAutomation` | library | `VibeEdit/Core/Automation` | Command specs, registry, socket, wire format, UI actions |
| `VibeEditAgent` | library | `VibeEdit/Core/Agent` | Agent providers, model adapters, sessions, credentials |
| `VibeEditPlugins` | library | `VibeEdit/Core/Plugins` | Capability service and adapters |
| `VibeEditDocument` | library | `VibeEdit/Core/Services` | Controllers, job center, export and proxy queues |
| `VibeEditCLI` | executable (`vibeedit`) | `CLI/` | Embedded in the app bundle |
| `VibeEditMCP` | executable (`vibeedit-mcp`) | `MCPBridge/` | Embedded in the app bundle |
| `vibeedit-bench` | executable | `Tools/Bench` | Not part of the app |
| `vibeedit-fixtures` | executable | `Tools/Fixtures` | Not part of the app; `Fixtures/make-media.sh` runs it |
| `VibeEditTestSupport` | library | `Tests/VibeEditTestSupport` | Test-only fixtures |
| `VibeEdit<Module>Tests` | test | `Tests/` | One per app library |
| `VibeEditProject`, `VibeEditPlugin`, `VibeEditImport`, `VibeEditInterchange` | library | `Packages/VibeEditCore/Sources` | Core package products |
| `VibeEditProjectFixtures` | library | `Packages/VibeEditCore/Tests` | Test-only fixtures |
| `VibeEdit<Module>Tests` (core) | test | `Packages/VibeEditCore/Tests` | One per core module |

In `project.yml`:

| Xcode target | Type | Notes |
|---|---|---|
| `VibeEdit` | application | macOS 14.0+, bundle ID `app.vibeedit`; embeds `vibeedit` and `vibeedit-mcp` in `Contents/MacOS` |
| `VibeEditCLI` | tool | Product name `vibeedit` |
| `VibeEditMCP` | tool | Product name `vibeedit-mcp` |
| `VibeEditTests` | unit-test bundle | Compiles every `Tests/*Tests` folder into one bundle; SwiftPM runs them as per-module targets |

## Plugin bundle and catalog layout

Plugins are discovered in three roots, highest priority first:

```text
<project>/.vibeedit/plugins/<plugin-id>/            # project override
~/Library/Application Support/VibeEdit/Plugins/<plugin-id>/
VibeEdit.app/Contents/Resources/Plugins/<plugin-id>/ # core plugins (bundled providers)
    ├── plugin.json                                # vibeedit.plugin/1 manifest
    └── <entrypoint>                               # executable named by the manifest; called with `rpc`
```

Request outputs live in project-scoped, provider-specific request folders and are validated before they become
project media. Plugin and provider IDs are stable; model files, virtual environments and downloaded dependencies
belong to the plugin, never to the timeline schema. See [plugins.md](../guides/plugins.md).
