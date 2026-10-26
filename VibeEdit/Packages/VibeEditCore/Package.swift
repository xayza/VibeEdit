// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "VibeEditCore",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "VibeEditProject", targets: ["VibeEditProject"]),
        .library(name: "VibeEditPlugin", targets: ["VibeEditPlugin"]),
        .library(name: "VibeEditImport", targets: ["VibeEditImport"]),
        .library(name: "VibeEditInterchange", targets: ["VibeEditInterchange"]),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-collections", from: "1.1.4")
    ],
    targets: [
        .target(name: "VibeEditProject", dependencies: [
            .product(name: "DequeModule", package: "swift-collections")
        ]),
        .target(name: "VibeEditPlugin", dependencies: ["VibeEditProject"]),
        .target(name: "VibeEditImport", dependencies: ["VibeEditProject"]),
        .target(name: "VibeEditInterchange", dependencies: ["VibeEditProject"]),
        // Tests: one target per module; shared project fixtures live in VibeEditProjectFixtures.
        .target(name: "VibeEditProjectFixtures", dependencies: ["VibeEditProject"], path: "Tests/VibeEditProjectFixtures"),
        // `swift run -c release vibeedit-core-bench`: core edit, validation and history cost at scale.
        .executableTarget(name: "vibeedit-core-bench", dependencies: ["VibeEditProject"], path: "Benchmarks/CoreBench"),
        .testTarget(name: "VibeEditProjectTests", dependencies: ["VibeEditProject", "VibeEditProjectFixtures"]),
        .testTarget(name: "VibeEditPluginTests", dependencies: ["VibeEditPlugin", "VibeEditProject", "VibeEditProjectFixtures"]),
        .testTarget(name: "VibeEditImportTests", dependencies: ["VibeEditImport", "VibeEditProject"]),
        .testTarget(name: "VibeEditInterchangeTests", dependencies: ["VibeEditInterchange", "VibeEditImport", "VibeEditProject"]),
    ]
)
